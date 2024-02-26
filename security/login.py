from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
import httpx
from jose import jwt
from pydantic import EmailStr
from config import Env, get_db, getEnv
from sqlalchemy.orm import Session
from mailing import send_activation_link_mail_to_user

from models.user import (
    AccountStatus,
    Register,
    UserDB,
    UserType,
    WorkerDB,
    create_user,
    create_user_social,
    get_user_by_email,
    update_user_password,
    update_user_status,
    update_worker_password,
    update_worker_status,
    validate_password,
)
from owners.routes import ownersRouter
from security.users import verify_user_activation_link
from security.workers import verify_worker_activation_link
from workers.routes import workersRouter
from users.routes import usersRouter
from security.token import get_password_hash, verify_password, Token
from passlib.exc import UnknownHashError
from google.oauth2 import id_token
from google.auth.transport import requests

loginRouter = APIRouter()


async def authenticate_user(
    db: Session, email: str, user_type: UserType, password: str
) -> UserDB:
    user: UserDB | WorkerDB = await get_user_by_email(db, email, user_type)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, getEnv().secret_key, algorithm=getEnv().algorithm
    )
    return encoded_jwt


@loginRouter.post(ownersRouter.prefix + "/login", response_model=Token)
@loginRouter.post(usersRouter.prefix + "/login", response_model=Token)
@loginRouter.post(workersRouter.prefix + "/login", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    user_type = (
        {
            ownersRouter.prefix + "/login": UserType.owner,
            usersRouter.prefix + "/login": UserType.user,
            workersRouter.prefix + "/login": UserType.worker,
        }
    )[request.scope["route"].path]
    user: UserDB | WorkerDB = await authenticate_user(
        db=db,
        email=form_data.username,
        password=form_data.password,
        user_type=user_type,
    )
    if not user:
        raise HTTPException(
            status_code=400, detail="Podano nieprawidłowy adres e-mail lub hasło"
        )
    access_token_expires = timedelta(minutes=getEnv().access_token_expire_minutes)
    name = (
        user.first_name
        if isinstance(user, UserDB)
        else f"{user.first_name} {user.surname}"
    )
    access_token = create_access_token(
        data={
            "sub": user.email,
            "scopes": user.permissions if isinstance(user, WorkerDB) else "",
            "name": name,
        },
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "Bearer", "name": name}


@loginRouter.post(usersRouter.prefix + "/googlelogin")
async def google_login(
    db: Annotated[Session, Depends(get_db)], token: Annotated[str, Body(embed=True)]
):
    try:
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(), getEnv().google_oauth_client
        )
    except:
        raise HTTPException(status_code=401, detail="Błąd autoryzacji")
    user: UserDB = await get_user_by_email(db, idinfo["email"], UserType.user)
    if user is None:
        user = await create_user_social(db, idinfo["email"], idinfo["given_name"])
    access_token_expires = timedelta(minutes=getEnv().access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email, "scopes": "", "name": user.first_name},
        expires_delta=access_token_expires,
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "name": user.first_name,
    }


@loginRouter.post(workersRouter.prefix + "/update-password")
async def update_password(
    db: Annotated[Session, Depends(get_db)],
    data: Annotated[Register, Body()],
):
    if not validate_password(data.password):
        raise HTTPException(status_code=400, detail="Hasło nie spełnia wymagań")
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Hasła nie są identyczne")
    worker = await get_user_by_email(db, data.email, UserType.worker)
    if worker is None:
        raise HTTPException(status_code=400, detail="Nieprawidłowe konto")
    if (
        worker.status != AccountStatus.disabled
        and worker.status != AccountStatus.active
    ):
        raise HTTPException(
            status_code=400, detail="Nie można zaktualizować hasła temu kontu"
        )
    try:
        if (
            data.access_key is None
            or len(data.access_key) < 10
            or not verify_worker_activation_link(worker=worker, token=data.access_key)
        ):
            raise HTTPException(status_code=400, detail="Nieprawidłowy klucz")
    except UnknownHashError:
        raise HTTPException(status_code=400, detail="Nieprawidłowy klucz")
    await update_worker_password(
        db=db, worker_id=worker.id, hashed_password=get_password_hash(data.password)
    )
    await update_worker_status(db=db, worker_id=worker.id, status=AccountStatus.active)
    return {"message": "Hasło zapisano poprawnie!"}


@loginRouter.post(usersRouter.prefix + "/register")
async def register(
    db: Annotated[Session, Depends(get_db)],
    data: Annotated[Register, Body()],
):
    if not validate_password(data.password):
        raise HTTPException(status_code=400, detail="Hasło nie spełnia wymagań")
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Hasła nie są identyczne")
    if data.name is None or len(data.name) < 3:
        raise HTTPException(status_code=400, detail="Nieprawidłowe imię")
    user = await get_user_by_email(db, data.email, UserType.user)
    if user is not None:
        if user.hashed_password is not None:
            raise HTTPException(status_code=400, detail="Konto już istnieje")
        else:
            await update_user_password(
                db=db, user_id=user.id, hashed_password=get_password_hash(data.password)
            )
            return {"message": "Konto zarejestrowano pomyślnie. Możesz się zalogować"}
    user = await create_user(
        db, data.email, data.name, get_password_hash(data.password)
    )
    await send_activation_link_mail_to_user(user)
    return {"message": "Link aktwacyjny znajdziesz na swojej skrzynce e-mail"}


@loginRouter.get(usersRouter.prefix + "/activate")
async def activate_account(
    db: Annotated[Session, Depends(get_db)], token: str, email: EmailStr
):
    user = await get_user_by_email(db, email, UserType.user)
    if user is None:
        raise HTTPException(status_code=400, detail="Nieprawidłowe konto")
    if user.status != AccountStatus.disabled:
        raise HTTPException(status_code=400, detail="Nie można aktywować konta")
    try:
        if (
            token is None
            or len(token) < 10
            or not verify_user_activation_link(user=user, token=token)
        ):
            raise HTTPException(status_code=400, detail="Nieprawidłowy klucz")
    except UnknownHashError:
        raise HTTPException(status_code=400, detail="Nieprawidłowy klucz")
    await update_user_status(db, user.id, AccountStatus.active)
    return "Konto aktywowane poprawnie"
