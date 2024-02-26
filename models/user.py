from __future__ import annotations
from enum import Enum
from typing import Literal
from fastapi import Depends
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import ForeignKey, Integer, String
from config import Base
from sqlalchemy.orm import relationship, Session, mapped_column
from sqlalchemy import Enum as SQLEnum
import re

class UserType(str, Enum):
    user = "user"
    owner = "owner"
    worker = "worker"

class AccountStatus(str, Enum):
    active = "Aktywny"
    disabled = "Nieaktywny"
    deleted = "Usunięty"
    blocked = "Zablokowany"

class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    first_name: str
    status: AccountStatus = AccountStatus.active
    user_type: UserType = UserType.user

class UserDB(Base):
    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True, index=True)
    email = mapped_column(String, unique=True, index=True)
    first_name = mapped_column(String)
    hashed_password = mapped_column(String)
    status = mapped_column(SQLEnum(AccountStatus), default=AccountStatus.active)
    user_type = user_type = mapped_column(SQLEnum(UserType), default = UserType.user)
    reservations = relationship("ReservationDB", back_populates="user_obj")

class Worker(User):
    model_config = ConfigDict(from_attributes=True)
    surname: str
    restaurant: RestaurantFull
    permissions: str = 'worker:basic'

class Owner(Worker):
    permissions: str = 'worker:basic owner:basic'
    user_type: Literal[UserType.owner]

class WorkerDB(Base):
    __tablename__ = "workers"
    id = mapped_column(Integer, primary_key=True, index=True)
    email = mapped_column(String, unique=True, index=True)
    first_name = mapped_column(String)
    hashed_password = mapped_column(String)
    status = mapped_column(SQLEnum(AccountStatus), default=AccountStatus.disabled)
    surname = mapped_column(String)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"),nullable=False)
    permissions = mapped_column(String, default = 'worker:basic')
    user_type = mapped_column(SQLEnum(UserType), default = UserType.worker)

    restaurant = relationship("RestaurantDB", foreign_keys=[restaurant_id], back_populates="workers")

class CreateUser(BaseModel):
    email: EmailStr
    first_name: str
    password: str

class CreateWorker(BaseModel):
    email: EmailStr
    first_name: str
    surname: str

class CreateWorkerDB(CreateWorker):
    restaurant: int

class WorkerListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    first_name: str
    surname: str
    status: AccountStatus

class Register(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str
    name: str | None = None
    access_key: str | None = None


def get_user_from_data(data: dict):
    if data['user_type'] == UserType.owner:
        return Owner(data)
    if data['user_type'] == UserType.worker:
        return Worker(data)
    return User(data)

def validate_password(password: str) -> bool:
    if re.search('[!@#$%^&*(),.]',password) is None:
        return False
    if re.search('[0-9]',password) is None:
        return False
    if re.search('[a-z]',password) is None:
        return False
    if re.search('[A-Z]',password) is None:
        return False
    if len(password) < 8:
        return False
    return True

async def get_user(db: Session, id: int, type: UserType) -> UserDB | WorkerDB | None:
    table = UserDB if type == UserType.user else WorkerDB 
    return db.query(table).filter(table.id == id).filter(table.user_type == type).first()

async def get_user_by_email(db: Session, email: EmailStr, type: UserType) -> UserDB | WorkerDB | None:
    table = UserDB if type == UserType.user else WorkerDB
    return db.query(table).filter(table.email == email).filter(table.user_type == type).first()

async def create_user_social(db: Session, email: EmailStr, first_name: str) -> UserDB:
    new_user = UserDB(email = email, first_name = first_name, status= AccountStatus.active)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

async def create_user(db: Session, email: EmailStr, first_name: str, password: str) -> UserDB:
    new_user = UserDB(email = email, first_name = first_name, status= AccountStatus.disabled, hashed_password = password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

async def insert_worker(db: Session, worker: CreateWorkerDB):
    new_worker = WorkerDB(
        email = worker.email,
        first_name = worker.first_name,
        surname = worker.surname,
        restaurant_id = worker.restaurant,
        hashed_password = ""
    )
    db.add(new_worker)
    db.commit()
    db.refresh(new_worker)
    return new_worker

async def restore_deleted_worker(db: Session, worker: WorkerDB, worker_data: CreateWorker):
    worker.status= AccountStatus.disabled
    worker.hashed_password =""
    worker.first_name= worker_data.first_name
    worker.surname = worker_data.surname
    db.commit()
    db.refresh(worker)
    return worker

async def get_restaurant_workers(db: Session, restaurant_id: int) -> list[WorkerListItem]:
    return db.query(WorkerDB)\
        .filter(WorkerDB.restaurant_id == restaurant_id)\
        .filter(WorkerDB.user_type == UserType.worker)\
        .filter(WorkerDB.status != AccountStatus.deleted)\
        .order_by(WorkerDB.surname)

async def update_worker_status(db:Session, worker_id: int, status: AccountStatus) -> None:
    db.query(WorkerDB).filter(WorkerDB.id == worker_id).update({'status': status})
    db.commit()

async def update_worker_password(db:Session, worker_id: int, hashed_password: str) -> None:
    db.query(WorkerDB).filter(WorkerDB.id == worker_id).update({'hashed_password': hashed_password}) 
    db.commit()

async def update_user_status(db:Session, user_id: int, status: AccountStatus) -> None:
    db.query(UserDB).filter(UserDB.id == user_id).update({'status': status})
    db.commit()

async def update_user_password(db:Session, user_id: int, hashed_password: str) -> None:
    db.query(UserDB).filter(UserDB.id == user_id).update({'hashed_password': hashed_password}) 
    db.commit()

from models.restaurant import RestaurantFull
Worker.update_forward_refs()
