from __future__ import annotations
from datetime import datetime, timedelta
from enum import Enum
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Enum as SQLEnum,
    String,
    desc,
)
from sqlalchemy.dialects.postgresql import JSONB
from config import Base, getEnv
from sqlalchemy.orm import relationship, mapped_column, Session
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.sql.functions import concat

from models.user import Worker




class ReservationStatus(str, Enum):
    pending = "Oczekująca"
    rejected = "Odrzucona"
    accepted = "Zaakceptowana"


class AddReservation(BaseModel):
    restaurant_id: int
    table: str | int | None = None
    date: datetime
    guests_amount: int


class Reservation(BaseModel):
    id: int
    restaurant_id: int
    name: str
    table: int | None = None
    date: datetime
    status: ReservationStatus
    guests_amount: int
    order: dict[str, dict]
    need_service: bool
    additional_details: str
    reservation_hour_length: float
    table_id: str | None = None


class ReservationDB(Base):
    __tablename__ = "reservations"

    id = mapped_column(Integer, primary_key=True, index=True)
    user = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    table = mapped_column(Integer, ForeignKey("restaurant_tables.id"), nullable=True)
    date = mapped_column(DateTime, nullable=False)
    status = mapped_column(
        SQLEnum(ReservationStatus), default=ReservationStatus.pending, nullable=False
    )
    guests_amount = mapped_column(Integer, nullable=False)
    order = mapped_column(JSONB, nullable=True)
    additional_details = mapped_column(String(160), nullable=False, default="")
    need_service = mapped_column(Boolean, nullable=False, default=False)
    restaurant = relationship(
        "RestaurantDB", foreign_keys=[restaurant_id], back_populates="reservations"
    )
    user_obj = relationship("UserDB", foreign_keys=[user], back_populates = "reservations")
    table_obj = relationship("RestaurantTableDB",foreign_keys=[table], back_populates="reservations")


async def create_reservation(db: Session, data: AddReservation, user_id: int):
    new_reservation = ReservationDB(
        restaurant_id=data.restaurant_id,
        table=data.table,
        date=data.date,
        status=ReservationStatus.pending,
        guests_amount=data.guests_amount,
        order={},
        user=user_id,
    )
    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)
    return new_reservation

async def create_waiter_reservation(db: Session, worker: Worker, table_id: int):
    new_reservation = ReservationDB(
        restaurant_id=worker.restaurant_id,
        table=table_id,
        date=datetime.now(),
        status=ReservationStatus.accepted,
        guests_amount=1,
        order={},
        user=None,
        additional_details = "Rezerwacja stworzona przez kelnera - " + worker.first_name + " " + worker.surname
    )
    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)
    return new_reservation


async def cancel_reservation(db: Session, reservation_id: int, user_id: int) -> bool:
    reservation = (
        db.query(ReservationDB)
        .filter(
            ReservationDB.user == user_id,
            ReservationDB.id == reservation_id,
            ReservationDB.status != ReservationStatus.rejected,
            ReservationDB.date >= datetime.now(),
        )
        .first()
    )
    if reservation is not None:
        db.delete(reservation)
        db.commit()
        return True
    return False


async def toggle_needs_service(db: Session, reservation_id: int, user_id: int):
    reservation = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            ReservationDB.user == user_id,
            ReservationDB.id == reservation_id,
            ReservationDB.status == ReservationStatus.accepted,
        )
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now()
        )
        .filter(ReservationDB.date < datetime.now())
        .first()
    )
    if reservation is not None:
        reservation.need_service = not reservation.need_service
        db.commit()
        db.refresh(reservation)
        return reservation
    return False


async def update_reservation_order(
    db: Session, reservation_id: int, user_id: int | None, order: dict[int, int]
) -> bool:
    filters = [
            ReservationDB.id == reservation_id,
            ReservationDB.status == ReservationStatus.accepted,
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
    ]
    if user_id is not None:
        filters.append(ReservationDB.user == user_id)
    reservation = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(*filters)
        .first()
    )
    restaurant_items = (
        db.query(RestaurantMenuItemDB)
        .join(
            RestaurantMenuCategoryDB,
            RestaurantMenuItemDB.category_id == RestaurantMenuCategoryDB.id,
        )
        .join(RestaurantDB, RestaurantMenuCategoryDB.restaurant_id == RestaurantDB.id)
        .filter(
            RestaurantMenuItemDB.status != RestaurantMenuItemType.inactive,
            RestaurantMenuCategoryDB.is_visible == True,
        ).all()
    )
    new_order : dict[int,int] = dict()
    for item_id in order:
        item_in_menu = next((x for x in restaurant_items if x.id == item_id), None)
        if item_in_menu is None:
            return False
        if str(item_id) not in reservation.order and item_in_menu.status != RestaurantMenuItemType.available:
            return False
        if str(item_id) in reservation.order and order[item_id] != reservation.order[str(item_id)]['count'] and item_in_menu.status == RestaurantMenuItemType.unavailable:
            return False
        new_order[item_id] = {"count": order[item_id], "name": item_in_menu.name, "total_price":"{:.2f}".format(item_in_menu.price*order[item_id]).replace('.',',')+" zł"}
    reservation.order=new_order
    db.commit()
    db.refresh(reservation)
    return True
   
async def get_reservation(db: Session, reservation_id: int, user_id: int | None) -> ReservationDB | None:
    filters = [
            ReservationDB.id == reservation_id,
            ReservationDB.status != ReservationStatus.rejected,
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
    ]
    if user_id is not None:
        filters.append(ReservationDB.user == user_id)
    return (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(*filters)
        .first()
    )


async def get_current_user_reservations(db: Session, user_id: int) -> list[Reservation]:
    reservationsDB = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(ReservationDB.user == user_id)
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now()
        )
        .order_by(ReservationDB.date)
        .all()
    )
    return [
        Reservation(
            **x.to_dict(),
            name=x.restaurant.name,
            reservation_hour_length=x.restaurant.reservation_hour_length,
        )
        for x in reservationsDB
    ]

async def get_restaurant_todays_reservations(db: Session, restaurant_id: int) -> list[Reservation]:
    reservationsDB = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            RestaurantDB.id == restaurant_id,
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
            func.cast(ReservationDB.date, Date) == datetime.now().date(),
            ReservationDB.status == ReservationStatus.accepted
        )
        .order_by(ReservationDB.date)
        .all()
    )
    return [
        Reservation(
            **x.to_dict(),
            name=('Kelner' if x.user_obj is None else x.user_obj.first_name) + " - Stolik " + x.table_obj.real_id,
            reservation_hour_length=x.restaurant.reservation_hour_length,
            table_id = x.table_obj.real_id
        )
        for x in reservationsDB
    ]

async def get_restaurant_table_coming_reservations_count(db: Session, restaurant_id: int, table_real_id: str) -> dict[int,int]:
    end_date = datetime.now() + timedelta(days=6)
    day_of_week_counts = (
        db.query(func.cast(ReservationDB.date, Date), func.extract('DOW',ReservationDB.date), func.count(ReservationDB.id))
        .join(RestaurantDB, ReservationDB.restaurant_id == RestaurantDB.id)
        .join(RestaurantTableDB, RestaurantTableDB.id == ReservationDB.table)
        .join(RestaurantHoursDB, RestaurantHoursDB.restaurant_id == RestaurantDB.id)
        .filter(
            RestaurantHoursDB.closed == False,
            RestaurantDB.id == restaurant_id,
            RestaurantTableDB.real_id == table_real_id,
            RestaurantHoursDB.day_of_week == func.extract('DOW',ReservationDB.date),
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
            func.cast(ReservationDB.date, Date) <= end_date,
            ReservationDB.status == ReservationStatus.accepted
        )
        .group_by(func.cast(ReservationDB.date, Date), func.extract('DOW',ReservationDB.date))
        .order_by(func.cast(ReservationDB.date, Date))
        .all()
    )
    # including zeroes
    count_dict: dict[int,int] = {int(x[1]):x[2] for x in day_of_week_counts}
    opened_days_of_week = db.query(RestaurantHoursDB.day_of_week).filter(RestaurantHoursDB.restaurant_id==restaurant_id, RestaurantHoursDB.closed == False).all()
    for day in opened_days_of_week:
        if day[0] not in count_dict:
            count_dict[day[0]]=0
    # ordering
    today_weekday = datetime.today().weekday()
    i = 0
    return_dict: dict[int, int] = {}
    while i < 7 :
        i+=1
        if today_weekday in count_dict:
            return_dict[today_weekday] = count_dict[today_weekday]
        today_weekday = 0 if today_weekday == 6 else today_weekday+1
    return return_dict

async def get_restaurant_pending_reservations(db: Session, restaurant_id: int) -> list[Reservation]:
    reservationsDB = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            RestaurantDB.id == restaurant_id,
            ReservationDB.date + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
            ReservationDB.status == ReservationStatus.pending
        )
        .order_by(ReservationDB.date)
        .all()
    )
    return [
        Reservation(
            **x.to_dict(),
            name=x.user_obj.first_name + " - Stolik " + x.table_obj.real_id,
            reservation_hour_length=x.restaurant.reservation_hour_length,
            table_id = x.table_obj.real_id
        )
        for x in reservationsDB
    ]

async def get_restaurant_current_reservations(db: Session, restaurant_id: int, page: int = 1, limit_per_page: int = 12) -> list[Reservation]:
    page_start = (page - 1) * limit_per_page
    page_end = page_start + limit_per_page
    end_date = datetime.now().date() + timedelta(days=6)
    reservationsDB = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            RestaurantDB.id == restaurant_id,
            ReservationDB.date + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
            ReservationDB.date
            <= end_date,
            ReservationDB.status == ReservationStatus.accepted
        )
        .order_by(ReservationDB.date)
        .slice(page_start, page_end)
        .all()
    )
    print(reservationsDB[0].id)
    return [
        Reservation(
            **x.to_dict(),
            name=('Kelner' if x.user_obj is None else x.user_obj.first_name) + " - Stolik " + x.table_obj.real_id,
            reservation_hour_length=x.restaurant.reservation_hour_length,
            table_id = x.table_obj.real_id
        )
        for x in reservationsDB
    ]

async def get_restaurant_pending_reservations_count(db: Session, restaurant_id: int) -> int:
    return (
        db.query(ReservationDB.id)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            RestaurantDB.id == restaurant_id,
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
            ReservationDB.status == ReservationStatus.pending
        )
        .count()
    )

async def get_restaurant_needing_service_reservations_count(db: Session, restaurant_id: int) -> int:
    return (
        db.query(ReservationDB.id)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            RestaurantDB.id == restaurant_id,
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now(),
            ReservationDB.date < datetime.now(),
            ReservationDB.status == ReservationStatus.accepted,
            ReservationDB.need_service == True
        )
        .count()
    )


async def update_pending_reservation_status(db: Session, reservation_id: int, restaurant_id: int, accepted: bool):
    reservation = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            RestaurantDB.id == restaurant_id,
            ReservationDB.id == reservation_id,
            ReservationDB.status == ReservationStatus.pending,
        )
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now()
        )
        .first()
    )
    if reservation is not None:
        reservation.status = ReservationStatus.accepted if accepted else ReservationStatus.rejected
        db.commit()
        db.refresh(reservation)
        return True
    return False


async def does_current_user_have_ongoing_reservations(
    db: Session, user_id: int
) -> bool:
    reservationsDB = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(ReservationDB.user == user_id)
        .filter(ReservationDB.status == ReservationStatus.accepted)
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now()
        )
        .filter(ReservationDB.date < datetime.now())
        .order_by(ReservationDB.date)
        .all()
    )
    return len(reservationsDB) > 0


async def get_current_user_reservations_history(
    db: Session, user_id: int, page: int = 1, limit_per_page: int = 8
) -> list[Reservation]:
    page_start = (page - 1) * limit_per_page
    page_end = page_start + limit_per_page
    reservationsDB = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(ReservationDB.user == user_id)
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            < datetime.now()
        )
        .order_by(desc(ReservationDB.date))
        .slice(page_start, page_end)
        .all()
    )
    return [
        Reservation(
            **x.to_dict(),
            name=x.restaurant.name,
            reservation_hour_length=x.restaurant.reservation_hour_length,
        )
        for x in reservationsDB
    ]

async def update_reservation_additional_details(db: Session, user_id: int, reservation_id: int, new_details: str) -> bool:
    reservation = (
        db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            ReservationDB.user == user_id,
            ReservationDB.id == reservation_id,
            ReservationDB.status == ReservationStatus.accepted,
        )
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now()
        )
        .first()
    )
    if reservation is not None and len(new_details)<240:
        reservation.additional_details = new_details
        db.commit()
        db.refresh(reservation)
        return True
    return False


from models.menu import (
    RestaurantMenuCategoryDB,
    RestaurantMenuItemDB,
    RestaurantMenuItemType,
)
from models.restaurant import RestaurantDB, RestaurantHoursDB
from models.table import RestaurantTableDB