from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import (
    OAuth2PasswordBearer,
    SecurityScopes
)
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from config import get_db, getEnv
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from models.user import AccountStatus, User, UserDB, UserType, Worker, get_user_by_email

class Token(BaseModel):
    access_token: str
    token_type: str
    name: str

class TokenData(BaseModel):
    email: str | None = None
    scopes: list[str] = []

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login",
    scopes = {
        "user:basic": "User privileges",
        "worker:basic": "Basic restaurant worker privileges",
        "owner:basic": "Basic company owner privileges"
    }
)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)

async def get_current_user(db: Annotated[Session, Depends(get_db)], request: Request, token: Annotated[str, Depends(oauth2_scheme)], security_scopes: SecurityScopes):
    if security_scopes.scopes:
        auth_value = f'Bearer scope={security_scopes.scope_str}'
    else:
        auth_value='Bearer'
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Działanie nieautoryzowane",
        headers={"WWW-Authenticate": auth_value},
    )
    try:
        payload = jwt.decode(token, getEnv().secret_key, algorithms=[getEnv().algorithm])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_scopes = payload.get("scopes", "").split()
        token_data = TokenData(scopes=token_scopes, email=email)
    except JWTError:
        raise credentials_exception
    
    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            raise credentials_exception
    
    if request.url.__str__().find('/owners/') != -1:
        user_type = UserType.owner
    elif request.url.__str__().find('/workers/') != -1:
        user_type = UserType.worker
    else:
        user_type = UserType.user
    user = await get_user_by_email(db = db ,email = token_data.email, type = user_type)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> Worker | User:
    if current_user.status != AccountStatus.active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user