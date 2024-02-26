from __future__ import annotations
import datetime
from email_validator import EmailNotValidError
from pydantic import BaseModel, EmailStr, validate_email
from sqlalchemy import Float, ForeignKey, Integer, String, Boolean, Time
from config import Base
from sqlalchemy.orm import relationship, mapped_column, Session
from mpu import haversine_distance
import re


class RestaurantBase(BaseModel):
    id: int
    name: str
    photo_url: str


class RestaurantSearch(BaseModel):
    search_name: str
    days_available: set[int]
    latitude: float
    longitude: float
    time_start: int
    time_end: int
    guests_amount: int
    distance_in_km: int
    has_free_tables: bool | None = None

    def is_data_valid(self) -> bool:
        if len(self.search_name) < 0 or len(self.search_name) > 64:
            return False
        if any(x > 6 or x < 0 for x in self.days_available):
            return False
        if (
            self.latitude > 90
            or self.latitude < -90
            or self.longitude >= 180
            or self.longitude < -180
        ):
            return False
        if self.time_start < 0 or self.time_end > 24 or self.time_end < self.time_start:
            return False
        if self.guests_amount < 0 or self.guests_amount > 8:
            return False
        if self.distance_in_km < 1 or self.distance_in_km > 15:
            return False
        return True


class RestaurantFull(RestaurantBase):
    nip: str
    country: str
    city: str
    street_number: str
    postal_code: str
    latitude: float
    longitude: float
    email: str
    phone_number: str
    plan_precision: int
    photo_url: str
    reservation_hour_length: float


class RestaurantHour(BaseModel):
    open_time: str
    close_time: str
    temporary: bool
    closed: bool


class RestaurantFlags(BaseModel):
    id: int
    name: str
    description: str or None
    setting: bool


class UpdateRestaurantInfo(BaseModel):
    email: str
    phone_number: str
    reservation_hour_length: float
    opening_hours: dict[int, RestaurantHour]
    flags: list[RestaurantFlags]

    def isDataValid(self) -> str:
        if (
            len(self.phone_number) < 5
            or len(self.phone_number) > 18
            or self.phone_number[0] != "+"
            or not self.phone_number[1:].isdigit()
        ):
            return "Niewłaściwy numer telefonu"
        try:
            validate_email(self.email)
        except EmailNotValidError:
            return "Niewłaściwy adres email"
        self.flags.sort(key=lambda x: x.id)
        if len(self.flags) > 4 or len(self.flags) <= 0:
            return "Niepoprawne ustawienia checkboxów"
        if self.flags[2].setting and not self.flags[0].setting:
            return "Nieprawidłowe ustawienia restauracji: by klient mógł podejrzeć status stolika, trzeba włączyć podgląd sali"
        if (
            self.flags[3].setting
            and not self.flags[1].setting
            and (not self.flags[2].setting and not self.flags[0].setting)
        ):
            return "Niepoprawne ustawienia restauracji: by rezerwacje stolików przez klientów były możliwe, trzeba włączyć podgląd statusów stolika oraz sali lub obłożenie restauracji"
        if len(self.opening_hours) != 7:
            return "Ustawienia godzin otwarcia muszą obejmować wszystkie dni"
        for day in self.opening_hours:
            if day < 0 or day > 6:
                return "Niepoprawny dzień otwarcia"
            hour = self.opening_hours[day]
            if hour.closed and hour.open_time != "" and hour.close_time != "":
                return "Niepoprawne ustawienia godzin otwarcia: by ustalić dzień zamknięty, należy usunąć godziny otwarcia"
            if not hour.closed and hour.open_time == "" and hour.close_time == "":
                return "Godzina otwarcia lub zamknięcia nie może być pusta"
            if not hour.closed:
                return ""
            if (
                re.search("^(:?[01][0-9]|2[0-3]):[0-5][0-9]$", hour.open_time) is None
                or re.search("^(:?[01][0-9]|2[0-3]):[0-5][0-9]$", hour.close_time)
                is None
            ):
                return "Godziny otwarcia muszą być w formacie HH:MM"
            if hour.open_time >= hour.close_time:
                return "Godzina otwarcia musi być wcześniejsza niż godzina zamknięcia"
        return ""


class RestaurantInfo(RestaurantFull):
    opening_hours: dict[int, RestaurantHour]
    flags: list[RestaurantFlags]


class RestaurantDB(Base):
    __tablename__ = "restaurants"

    id = mapped_column(Integer, primary_key=True, index=True)
    name = mapped_column(String, nullable=False)
    nip = mapped_column(String, unique=True, index=True)
    country = mapped_column(String)
    city = mapped_column(String)
    street_number = mapped_column(String)
    postal_code = mapped_column(String)
    latitude = mapped_column(Float)
    longitude = mapped_column(Float)
    email = mapped_column(String)
    phone_number = mapped_column(String)
    plan_precision = mapped_column(Integer, nullable=True)
    reservation_hour_length = mapped_column(Float)
    photo_url = mapped_column(String)

    flags = relationship("RestaurantSettingsDB")
    workers = relationship("WorkerDB", back_populates="restaurant")
    tables = relationship("RestaurantTableDB", back_populates="restaurant")
    borders = relationship("RestaurantBorderDB", back_populates="restaurant")
    reservations = relationship("ReservationDB", back_populates="restaurant")
    categories = relationship(
        "RestaurantMenuCategoryDB",
        back_populates="restaurant",
        order_by="RestaurantMenuCategoryDB.order",
    )
    opening_hours = relationship("RestaurantHoursDB")


class RestaurantFlagDB(Base):
    __tablename__ = "restaurant_flags"

    id = mapped_column(Integer, primary_key=True, index=True)
    name = mapped_column(String, nullable=False)
    description = mapped_column(String)


class RestaurantSettingsDB(Base):
    __tablename__ = "restaurant_flag_settings"

    id = mapped_column(Integer, primary_key=True, index=True)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    flag_id = mapped_column(Integer, ForeignKey("restaurant_flags.id"), nullable=False)
    setting = mapped_column(Boolean, default=False)


class RestaurantHoursDB(Base):
    __tablename__ = "restaurant_opening_hours"
    id = mapped_column(Integer, primary_key=True, index=True)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    day_of_week = mapped_column(Integer)
    open_time = mapped_column(Time, nullable=True)
    close_time = mapped_column(Time, nullable=True)
    temporary = mapped_column(Boolean)
    closed = mapped_column(Boolean)


async def get_restaurant(db: Session, id: int) -> RestaurantFull:
    return db.query(RestaurantDB).filter(RestaurantDB.id == id).first()


async def get_restaurant_db(db: Session, id: int) -> RestaurantDB:
    return db.query(RestaurantDB).filter(RestaurantDB.id == id).first()


async def get_restaurant_flags(db: Session, id: int) -> list[RestaurantFlags]:
    flags = db.query(RestaurantFlagDB).all()
    restaurantFlags = (
        db.query(RestaurantSettingsDB)
        .filter(RestaurantSettingsDB.restaurant_id == id)
        .all()
    )
    restaurantFlags = {x.flag_id: x for x in restaurantFlags}
    returnFlags = []
    for flag in flags:
        if flag.id in restaurantFlags:
            returnFlags.append(
                RestaurantFlags(
                    **flag.to_dict(), setting=restaurantFlags[flag.id].setting
                )
            )
        else:
            newFlag = RestaurantSettingsDB(
                restaurant_id=id, flag_id=flag.id, setting=True
            )
            returnFlags.append(RestaurantFlags(**flag.to_dict(), setting=True))
            db.add(newFlag)
    if len(restaurantFlags) < len(flags):
        db.commit()
    return returnFlags


async def get_restaurant_hours(db: Session, id: int) -> dict[int, RestaurantHour]:
    hours = (
        db.query(RestaurantHoursDB).filter(RestaurantHoursDB.restaurant_id == id).all()
    )
    hoursDict = {x.day_of_week: x for x in hours}
    returnHours = dict()
    for i in range(7):
        if i in hoursDict:
            open_time = (
                ""
                if hoursDict[i].open_time is None
                else hoursDict[i].open_time.strftime("%H:%M")
            )
            close_time = (
                ""
                if hoursDict[i].close_time is None
                else hoursDict[i].close_time.strftime("%H:%M")
            )
            returnHours[i] = {
                "open_time": open_time,
                "close_time": close_time,
                "temporary": hoursDict[i].temporary,
                "closed": hoursDict[i].closed,
            }
        else:
            newHour = RestaurantHoursDB(
                restaurant_id=id,
                day_of_week=i,
                temporary=False,
                open_time=None,
                close_time=None,
                closed=True,
            )
            db.add(newHour)
            returnHours[i] = {
                "open_time": "",
                "close_time": "",
                "temporary": False,
                "closed": True,
            }
    if len(hoursDict) < 7:
        db.commit()
    return returnHours


async def update_precision(db: Session, restaurant_id: int, precision: int):
    db.query(RestaurantDB).filter(RestaurantDB.id == restaurant_id).update(
        {"plan_precision": precision}
    )
    db.commit()


async def update_restaurant_contact(
    db: Session, restaurant_id: int, email: EmailStr, phone_number: str
):
    db.query(RestaurantDB).filter(RestaurantDB.id == restaurant_id).update(
        {"phone_number": phone_number, "email": email}
    )
    db.commit()


async def update_restaurant_reservation_length(
    db: Session, restaurant_id: int, value: float
):
    db.query(RestaurantDB).filter(RestaurantDB.id == restaurant_id).update(
        {"reservation_hour_length": value}
    )
    db.commit()


async def update_restaurant_flags(
    db: Session, restaurant_id: int, flags: list[RestaurantFlags]
):
    previousFlags = (
        db.query(RestaurantSettingsDB)
        .filter(RestaurantSettingsDB.restaurant_id == restaurant_id)
        .all()
    )
    previousFlags = {x.flag_id: x for x in previousFlags}
    for flag in flags:
        if flag.id in previousFlags:
            previousFlags[flag.id].setting = flag.setting
        else:
            newFlag = RestaurantSettingsDB(
                restaurant_id=restaurant_id, flag_id=flag.id, setting=flag.setting
            )
            db.add(newFlag)
    db.commit()


async def update_restaurant_opening_hours(
    db: Session, restaurant_id: int, opening_hours: dict[int, RestaurantHour]
):
    previousHours = (
        db.query(RestaurantHoursDB)
        .filter(RestaurantSettingsDB.restaurant_id == restaurant_id)
        .all()
    )
    previousHours = {x.day_of_week: x for x in previousHours}
    for day in opening_hours:
        if day in previousHours:
            previousHours[day].open_time = (
                None
                if opening_hours[day].open_time == ""
                else opening_hours[day].open_time
            )
            previousHours[day].close_time = (
                None
                if opening_hours[day].close_time == ""
                else opening_hours[day].close_time
            )
            previousHours[day].temporary = opening_hours[day].temporary
            previousHours[day].closed = opening_hours[day].closed
        else:
            newHour = RestaurantHoursDB(
                restaurant_id=restaurant_id,
                day_of_week=day,
                open_time=None
                if opening_hours[day].open_time == ""
                else opening_hours[day].open_time,
                close_time=None
                if opening_hours[day].close_time == ""
                else opening_hours[day].close_time,
                temporary=opening_hours[day].temporary,
                closed=opening_hours[day].closed,
            )
            db.add(newHour)
    db.commit()


async def get_restaurant_photo(db: Session, restaurant_id: int):
    return (
        db.query(RestaurantDB.photo_url)
        .filter(RestaurantDB.id == restaurant_id)
        .scalar()
    )


async def update_restaurant_photo(
    db: Session, restaurant_id: int, photo_url: str
) -> str:
    oldUrl = await get_restaurant_photo(db=db, restaurant_id=restaurant_id)
    db.query(RestaurantDB).filter(RestaurantDB.id == restaurant_id).update(
        {"photo_url": photo_url}
    )
    db.commit()
    return oldUrl


async def get_restaurants_by_search(
    db: Session, options: RestaurantSearch
) -> list[RestaurantBase]:
    restaurants = db.query(RestaurantDB).all()
    print(options)
    if len(options.search_name) > 0:
        restaurants = filter(
            lambda x: options.search_name.lower() in x.name.lower(), restaurants
        )
    if options.has_free_tables is not None:
        new_restaurants = []
        if len(options.days_available) == 0:
            date = datetime.datetime.now()
            currentWeekday = int(date.strftime("%w")) - 1
            if currentWeekday < 0:
                currentWeekday = 6
            currentHour = date.time()
            for restaurant in restaurants:
                result = any(
                    (day := hour).day_of_week == currentWeekday
                    for hour in restaurant.opening_hours
                )
                if result and not day.closed:
                    reservation_close_time = (
                        datetime.datetime(
                            2000, 1, 1, day.close_time.hour, day.close_time.minute
                        )
                        - datetime.timedelta(hours=restaurant.reservation_hour_length)
                    ).time()
                if (
                    result
                    and not day.closed
                    and day.open_time < currentHour
                    and reservation_close_time
                    > currentHour + restaurant.reservation_hour_length
                ):
                    if options.has_free_tables:
                        tables = get_free_tables_for_time(
                            db, restaurant.id, date, options.guests_amount
                        )
                        if len(tables) > 0:
                            new_restaurants.append(restaurant)
                    else:
                        new_restaurants.append(restaurant)
        else:
            begin_time = datetime.time(options.time_start, 0, 0)
            end_time = datetime.time(options.time_end, 0, 0)
            for restaurant in restaurants:
                for day in options.days_available:
                    result = any(
                        (relevant_day := hour).day_of_week == day
                        for hour in restaurant.opening_hours
                    )
                    if result and not relevant_day.closed:
                        min_overlap = max(relevant_day.open_time,begin_time)
                        max_overlap = min(relevant_day.close_time,end_time)
                    if (
                        ((max_overlap.hour*60+ max_overlap.minute)/60 - (min_overlap.hour*60 + min_overlap.minute)/60) >= restaurant.reservation_hour_length
                    ):
                        new_restaurants.append(restaurant)
                        break
        restaurants = new_restaurants
    restaurants = filter(
        lambda x: haversine_distance(
            (options.latitude, options.longitude), (x.latitude, x.longitude)
        )
        < options.distance_in_km,
        restaurants,
    )
    restaurants = list(restaurants)
    restaurants.sort(
        key=lambda x: haversine_distance(
            (options.latitude, options.longitude), (x.latitude, x.longitude)
        )
    )
    return [RestaurantBase(**x.to_dict()) for x in restaurants]


from models.table import get_free_tables_for_time
