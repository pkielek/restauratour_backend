from __future__ import annotations
from datetime import date, datetime, timedelta
from enum import Enum
from pydantic import BaseModel
from sqlalchemy import ForeignKey, Integer, Boolean, Enum as SQLEnum, String, func, and_, cast, Date
from config import Base
from sqlalchemy.orm import relationship, mapped_column, Session
from itertools import product
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.sql.functions import concat



class Rect:
    def __init__(self, left: int, top: int, right: int, bottom: int):
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom

    left: int
    top: int
    right: int
    bottom: int

    def overlaps(self, other: Rect) -> bool:
        if self.right <= other.left or other.right <= self.left:
            return False
        if self.bottom <= other.top or other.bottom <= self.top:
            return False
        return True

    def __repr__(self):
        return repr(
            str(self.left)
            + ","
            + str(self.top)
            + ","
            + str(self.right)
            + ","
            + str(self.bottom)
        )


class RestaurantBorderType(str, Enum):
    window = "Okno"
    door = "Drzwi"
    wall = "Ściana"


class RestaurantTable(BaseModel):
    real_id: str
    left: int
    top: int
    width: int
    height: int
    seats_top: int
    seats_left: int
    seats_right: int
    seats_bottom: int

    def toRect(self, precision: int) -> Rect:
        return Rect(
            self.left - (precision if self.seats_left > 0 else 0),
            self.top - (precision if self.seats_top > 0 else 0),
            self.left + self.width + (precision if self.seats_right > 0 else 0),
            self.top + self.height + (precision if self.seats_bottom > 0 else 0),
        )


class RestaurantBorder(BaseModel):
    left: int
    top: int
    is_horizontal: bool
    length: int
    type: RestaurantBorderType

    def toRect(self, precision: int) -> Rect:
        return Rect(
            self.left,
            self.top,
            self.left + (self.length if self.is_horizontal else precision),
            self.top + (precision if self.is_horizontal else self.length),
        )

    def toBroadenedRect(self, precision: int) -> Rect:
        return Rect(
            self.left - (precision if self.is_horizontal else 0),
            self.top - (0 if self.is_horizontal else precision),
            self.left
            + ((self.length + precision) if self.is_horizontal else precision),
            self.top + (precision if self.is_horizontal else (self.length + precision)),
        )


class PlannerInfo(BaseModel):
    precision: int
    tables: list[RestaurantTable]
    borders: list[RestaurantBorder]

    def isDataValid(self) -> list[str]:
        errors = set()
        for i, table in enumerate(self.tables):
            for j in range(i + 1, len(self.tables)):
                if table.real_id == self.tables[j].real_id:
                    errors.add(
                        "Występuje kilka stołów o identyfikatorze równym:"
                        + table.real_id
                    )
                if table.toRect(self.precision).overlaps(
                    self.tables[j].toRect(self.precision)
                ):
                    errors.add(
                        "Stoliki o identyfikatorach "
                        + table.real_id
                        + " i "
                        + self.tables[j].real_id
                        + " nachodzą na siebie"
                    )
            for border in self.borders:
                if table.toRect(self.precision).overlaps(border.toRect(self.precision)):
                    errors.add(
                        "Stolik o identyfikatorze "
                        + table.real_id
                        + " nachodzi na granice"
                    )
                    break
            if table.left < 0 or table.top < 0:
                errors.add(
                    "Stolik o identyfikatorze "
                    + table.real_id
                    + " ma nieprawidłowe współrzędne"
                )
            if table.seats_left * self.precision > table.height or table.seats_left < 0:
                errors.add(
                    "Stolik o identyfikatorze "
                    + table.real_id
                    + " ma nieprawidłową liczbę stolików z lewej strony"
                )
            if (
                table.seats_right * self.precision > table.height
                or table.seats_right < 0
            ):
                errors.add(
                    "Stolik o identyfikatorze "
                    + table.real_id
                    + " ma nieprawidłową liczbę stolików z prawej strony"
                )
            if table.seats_top * self.precision > table.width or table.seats_top < 0:
                errors.add(
                    "Stolik o identyfikatorze "
                    + table.real_id
                    + " ma nieprawidłową liczbę stolików od góry"
                )
            if (
                table.seats_bottom * self.precision > table.width
                or table.seats_bottom < 0
            ):
                errors.add(
                    "Stolik o identyfikatorze "
                    + table.real_id
                    + " ma nieprawidłową liczbę stolików od dołu"
                )
        for i, border in enumerate(self.borders):
            if border.left < 0 or border.top < 0:
                errors.add("Granice mają nieprawidłowe współrzędne")
                break
            for j in range(i + 1, len(self.borders)):
                if border.toRect(self.precision).overlaps(
                    self.borders[j].toRect(self.precision)
                ):
                    errors.add("Granice nachodzą na siebie")
            if i > 0:
                if not border.toBroadenedRect(self.precision).overlaps(
                    self.borders[i - 1].toBroadenedRect(self.precision)
                ):
                    errors.add("Granice mają nieprawidłowe współrzędne")
        if (
            len(self.borders) >2 and not self.borders[-1]
            .toBroadenedRect(self.precision)
            .overlaps(self.borders[0].toBroadenedRect(self.precision))
        ):
            errors.add("Granica nie jest zamknięta")
        if self.precision < 15 or self.precision > 50:
            errors.add("Błędna wartość precyzji")
        return errors


class RestaurantTableDB(Base):
    __tablename__ = "restaurant_tables"

    id = mapped_column(Integer, primary_key=True, index=True)
    real_id = mapped_column(String, nullable=False)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    left = mapped_column(Integer, nullable=False)
    top = mapped_column(Integer, nullable=False)
    width = mapped_column(Integer, nullable=False)
    height = mapped_column(Integer, nullable=False)
    seats_top = mapped_column(Integer, nullable=False)
    seats_left = mapped_column(Integer, nullable=False)
    seats_right = mapped_column(Integer, nullable=False)
    seats_bottom = mapped_column(Integer, nullable=False)

    restaurant = relationship(
        "RestaurantDB", foreign_keys=[restaurant_id], back_populates="tables"
    )
    reservations = relationship("ReservationDB", back_populates="table_obj")


class RestaurantBorderDB(Base):
    __tablename__ = "restaurant_borders"

    id = mapped_column(Integer, primary_key=True, index=True)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    left = mapped_column(Integer, nullable=False)
    top = mapped_column(Integer, nullable=False)
    is_horizontal = mapped_column(Boolean, nullable=False)
    length = mapped_column(Integer, nullable=False)
    type = mapped_column(
        SQLEnum(RestaurantBorderType), default=RestaurantBorderType.wall
    )

    restaurant = relationship(
        "RestaurantDB", foreign_keys=[restaurant_id], back_populates="borders"
    )


async def get_restaurant_tables(
    db: Session, restaurant_id: int
) -> list[RestaurantTableDB]:
    return (
        db.query(RestaurantTableDB)
        .filter(RestaurantTableDB.restaurant_id == restaurant_id)
        .order_by(RestaurantTableDB.real_id)
    )


async def get_restaurant_borders(
    db: Session, restaurant_id: int
) -> list[RestaurantBorderDB]:
    return db.query(RestaurantBorderDB).filter(
        RestaurantBorderDB.restaurant_id == restaurant_id
    )


async def update_borders(
    db: Session, restaurant_id: int, newBorders: list[RestaurantBorder]
):
    db.query(RestaurantBorderDB).filter(
        RestaurantBorderDB.restaurant_id == restaurant_id
    ).delete()
    db.commit()
    db.add_all(
        [
            RestaurantBorderDB(**x.model_dump(), restaurant_id=restaurant_id)
            for x in newBorders
        ]
    )
    db.commit()


async def update_tables(
    db: Session, restaurant_id: int, newTables: list[RestaurantTable]
):
    alreadyPutTables = db.query(RestaurantTableDB).filter(
        RestaurantTableDB.restaurant_id == restaurant_id
    )
    tableDict = {table.real_id: table for table in alreadyPutTables}
    for table in newTables:
        if table.real_id in tableDict:
            tableDict[table.real_id].left = table.left
            tableDict[table.real_id].top = table.top
            tableDict[table.real_id].width = table.width
            tableDict[table.real_id].height = table.height
            tableDict[table.real_id].seats_top = table.seats_top
            tableDict[table.real_id].seats_left = table.seats_left
            tableDict[table.real_id].seats_right = table.seats_right
            tableDict[table.real_id].seats_bottom = table.seats_bottom
            tableDict.pop(table.real_id)
        else:
            newTable = RestaurantTableDB(
                **table.model_dump(), restaurant_id=restaurant_id
            )
            db.add(newTable)
    for tableToRemove in tableDict.values():
        pastReservations = (
            db.query(ReservationDB)
            .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
            .filter(
                RestaurantDB.id == restaurant_id,
                ReservationDB.table == tableToRemove.id,
                ReservationDB.date
                + func.cast(
                    concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
                )
                < datetime.now(),
            )
            .all()
        )
        incomingReservations = (
            db.query(ReservationDB)
            .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
            .filter(
                RestaurantDB.id == restaurant_id,
                ReservationDB.table == tableToRemove.id,
                ReservationDB.date
                + func.cast(
                    concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
                )
                >= datetime.now(),
            )
            .all()
        )
        for reservation in pastReservations:
            reservation.table = None
        for reservation in incomingReservations:
            db.delete(reservation)
        db.delete(tableToRemove)
    db.commit()


async def get_free_tables_for_time(
    db: Session,
    restaurant_id: int,
    date: datetime,
    guests_amount: int,
    table_id: str | None = None,
    end_date: datetime | None = None,
) -> list[RestaurantTableDB]:
    restaurant_reservation_length = (
        db.query(RestaurantDB.reservation_hour_length)
        .filter(RestaurantDB.id == restaurant_id)
        .scalar()
    )
    if end_date is None:
        end_date = date
    end_date = end_date + timedelta(hours=restaurant_reservation_length)

    filters = [
        RestaurantDB.id == restaurant_id,
        RestaurantTableDB.seats_bottom
        + RestaurantTableDB.seats_left
        + RestaurantTableDB.seats_right
        + RestaurantTableDB.seats_top
        >= guests_amount,
        ReservationDB.id == None,
    ]
    if table_id is not None:
        filters.append(RestaurantTableDB.real_id == table_id)

    return (
        db.query(RestaurantTableDB)
        .join(
            RestaurantDB,
            RestaurantTableDB.restaurant_id == RestaurantDB.id,
            isouter=True,
        )
        .join(
            ReservationDB,
            and_(
                RestaurantTableDB.id == ReservationDB.table,
                ReservationDB.date > date,
                ReservationDB.date < end_date,
                ReservationDB.status != ReservationStatus.rejected,
            ),
            isouter=True,
        )
        .filter(*filters)
    ).all()

async def is_table_free_now(
    db: Session,
    restaurant_id: int,
    table_id: str,
) -> RestaurantTableDB | None:
    restaurant_reservation_length = (
        db.query(RestaurantDB.reservation_hour_length)
        .filter(RestaurantDB.id == restaurant_id)
        .scalar()
    )
    date = datetime.now()
    end_date = date + timedelta(hours=restaurant_reservation_length)

    filters = [
        RestaurantDB.id == restaurant_id,
        ReservationDB.id == None,
        RestaurantTableDB.real_id == table_id,
    ]

    return (
        db.query(RestaurantTableDB)
        .join(
            RestaurantDB,
            RestaurantTableDB.restaurant_id == RestaurantDB.id,
            isouter=True,
        )
        .join(
            ReservationDB,
            and_(
                RestaurantTableDB.id == ReservationDB.table,
                ReservationDB.date > date,
                ReservationDB.date < end_date,
                ReservationDB.status == ReservationStatus.accepted,
            ),
            isouter=True,
        )
        .filter(*filters)
    ).first()

async def get_restaurant_free_timeslots_for_day(
    db:Session,
    restaurant_id: int,
    day: date,
    guests_amount: int
)->list[datetime]:
    restaurant_hours = db.query(RestaurantHoursDB).filter(RestaurantHoursDB.restaurant_id==restaurant_id,RestaurantHoursDB.day_of_week == day.weekday()).first()
    if restaurant_hours is None or restaurant_hours.closed:
        return []
    restaurant_reservation_length = (
        db.query(RestaurantDB.reservation_hour_length)
        .filter(RestaurantDB.id == restaurant_id)
        .scalar()
    )
    reservation_length = timedelta(hours=restaurant_reservation_length)
    start_date = datetime(day.year,day.month,day.day,restaurant_hours.open_time.hour,(restaurant_hours.open_time.minute // 15)*15,0)
    end_date = datetime(day.year,day.month,day.day,restaurant_hours.close_time.hour,(restaurant_hours.close_time.minute // 15)*15,0)
    interval = timedelta(minutes=15)
    date = start_date

    appropriate_tables = db.query(RestaurantTableDB.id).filter(RestaurantTableDB.seats_bottom
        + RestaurantTableDB.seats_left
        + RestaurantTableDB.seats_right
        + RestaurantTableDB.seats_top
        >= guests_amount, RestaurantTableDB.restaurant_id==restaurant_id).all()
    appropriate_tables_ids = [x[0] for x in appropriate_tables]
    day_reservations : list[ReservationDB] = db.query(ReservationDB.id,ReservationDB.date).filter(ReservationDB.restaurant_id==restaurant_id,ReservationDB.status != ReservationStatus.rejected,
        ReservationDB.table.in_(appropriate_tables_ids),cast(ReservationDB.date,Date) == day
    ).all()

    available_dates = []
    while date<=end_date:
        if len(list(filter(lambda x: not (date+reservation_length < x.date or x.date+reservation_length<date),day_reservations))) < len(appropriate_tables):
            available_dates.append(date)
        date = date + interval
    return available_dates

from models.reservation import ReservationDB, ReservationStatus

from models.restaurant import RestaurantDB, RestaurantHoursDB