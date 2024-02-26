from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Boolean,
    Enum as SQLEnum,
    Time,
    Float,
)
from config import Base, getEnv
from sqlalchemy.orm import relationship, mapped_column, Session
from sqlalchemy import func
from supabase import create_client, Client

from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.sql.functions import concat
from sqlalchemy.orm.attributes import flag_modified


class RestaurantMenuItemType(str, Enum):
    inactive = "Nieaktywny"
    unavailable = "Niedostępny"
    available = "Dostępny"


class RestaurantMenuItem(BaseModel):
    id: int
    name: str
    description: str
    price: float
    order: int
    status: RestaurantMenuItemType
    photo_url: Optional[str] = ""

class RestaurantMenuItemUser(BaseModel):
    id: int
    name: str
    description: str
    price: float
    order: int
    is_available: bool
    photo_url: Optional[str] = ""


class RestaurantMenuCategory(BaseModel):
    id: int
    name: str
    is_visible: bool
    order: int
    items: list[RestaurantMenuItem]


class RestaurantMenuCategoryUser(BaseModel):
    id: int
    name: str
    order: int


class RestaurantMenuFull(BaseModel):
    menu: list[RestaurantMenuCategory]
    photo_url: str

class RestaurantMenuUser(BaseModel):
    categories: list[RestaurantMenuCategoryUser]
    items: list[RestaurantMenuItemUser]

class RestaurantOrderUser(BaseModel):
    menu: RestaurantMenuUser
    current_order: dict[int,int]
    restaurant_id: int

class RestaurantMenuItemDB(Base):
    __tablename__ = "restaurant_menu_items"
    id = mapped_column(Integer, primary_key=True, index=True)
    category_id = mapped_column(Integer, ForeignKey("restaurant_menu_categories.id"))
    name = mapped_column(String, nullable=False)
    order = mapped_column(Integer, nullable=False)
    description = mapped_column(String, nullable=False)
    price = mapped_column(Float, nullable=False)
    status = mapped_column(
        SQLEnum(RestaurantMenuItemType), default=RestaurantMenuItemType.available
    )
    photo_url = mapped_column(String)
    category = relationship(
        "RestaurantMenuCategoryDB", foreign_keys=[category_id], back_populates="items"
    )


class RestaurantMenuCategoryDB(Base):
    __tablename__ = "restaurant_menu_categories"

    id = mapped_column(Integer, primary_key=True, index=True)
    restaurant_id = mapped_column(Integer, ForeignKey("restaurants.id"), nullable=False)
    name = mapped_column(String, nullable=False)
    order = mapped_column(Integer, nullable=False)
    is_visible = mapped_column(Boolean, nullable=False)
    items = relationship(
        "RestaurantMenuItemDB",
        back_populates="category",
        order_by=("RestaurantMenuItemDB.order"),
    )
    restaurant = relationship(
        "RestaurantDB", foreign_keys=[restaurant_id], back_populates="categories"
    )


async def get_restaurant_menu(
    db: Session, restaurant_id: int
) -> list[RestaurantMenuCategoryDB]:
    return (
        db.query(RestaurantMenuCategoryDB)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .order_by(RestaurantMenuCategoryDB.order)
        .all()
    )


async def get_restaurant_menu_visible_categories(
    db: Session, restaurant_id: int
) -> list[RestaurantMenuCategoryDB]:
    return (
        db.query(RestaurantMenuCategoryDB)
        .filter(
            RestaurantMenuCategoryDB.restaurant_id == restaurant_id,
            RestaurantMenuCategoryDB.is_visible == True,
        )
        .order_by(RestaurantMenuCategoryDB.order)
        .all()
    )
async def get_restaurant_menu_category_items(
    db: Session, restaurant_id: int, category_id: int,
) -> list[RestaurantMenuItemDB]:
    category = (
        db.query(RestaurantMenuCategoryDB)
        .filter(
            RestaurantMenuCategoryDB.restaurant_id == restaurant_id,
            RestaurantMenuCategoryDB.is_visible == True,
            RestaurantMenuCategoryDB.id == category_id
        )
        .first()
    )
    if category is None:
        raise HTTPException(400, "Brak kategorii")
    
    return (
        db.query(RestaurantMenuItemDB)
        .filter(
            RestaurantMenuItemDB.category_id == category_id,
            RestaurantMenuItemDB.status != RestaurantMenuItemType.inactive
        )
        .all()
    )

async def add_new_category(db: Session, restaurant_id: int):
    category_count = (
        db.query(RestaurantMenuCategoryDB)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .count()
    )
    max_order = (
        db.query(func.max(RestaurantMenuCategoryDB.order))
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .scalar()
    )
    new_category = RestaurantMenuCategoryDB(
        restaurant_id=restaurant_id,
        name="Kategoria" + str(category_count + 1),
        order=1 if max_order is None else max_order + 1,
        is_visible=True,
    )
    db.add(new_category)
    db.commit()


async def delete_restaurant_category(
    db: Session, restaurant_id: int, category_id: int
) -> bool:
    category_to_remove = (
        db.query(RestaurantMenuCategoryDB)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .filter(RestaurantMenuCategoryDB.id == category_id)
        .first()
    )
    if category_to_remove is not None:
        items_to_remove = (
            db.query(RestaurantMenuItemDB)
            .filter(RestaurantMenuItemDB.category_id == category_id)
            .all()
        )
        for item in items_to_remove:
            db.delete(item)
        db.delete(category_to_remove)
        db.commit()
        return True
    return False


async def update_category_visibility(
    db: Session, restaurant_id: int, category_id: int
) -> bool:
    category = (
        db.query(RestaurantMenuCategoryDB)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .filter(RestaurantMenuCategoryDB.id == category_id)
        .first()
    )
    if category is not None:
        category.is_visible = not category.is_visible
        db.commit()
        return True
    return False


async def update_categories_orders(
    db: Session, restaurant_id: int, category_id_1: int, category_id_2: int
) -> bool:
    categoriesSelected = (
        db.query(RestaurantMenuCategoryDB)
        .filter(
            RestaurantMenuCategoryDB.restaurant_id == restaurant_id,
            RestaurantMenuCategoryDB.id.in_([category_id_1, category_id_2]),
        )
        .order_by(RestaurantMenuCategoryDB.order)
        .all()
    )
    if len(categoriesSelected) != 2:
        return False
    categoriesToChange = (
        db.query(RestaurantMenuCategoryDB)
        .filter(
            RestaurantMenuCategoryDB.restaurant_id == restaurant_id,
            RestaurantMenuCategoryDB.order > categoriesSelected[0].order,
            RestaurantMenuCategoryDB.order < categoriesSelected[1].order,
        )
        .all()
    )
    for category in categoriesToChange:
        if categoriesSelected[0].id == category_id_1:
            category.order = category.order - 1
        else:
            category.order = category.order + 1
    if categoriesSelected[0].id == category_id_1:
        categoriesSelected[0].order, categoriesSelected[1].order = (
            categoriesSelected[1].order,
            categoriesSelected[1].order - 1,
        )
    else:
        categoriesSelected[0].order, categoriesSelected[1].order = (
            categoriesSelected[0].order + 1,
            categoriesSelected[0].order,
        )
    db.commit()
    return True


async def update_category_name(
    db: Session, restaurant_id: int, category_id: int, new_name: str
) -> bool:
    names = (
        db.query(RestaurantMenuCategoryDB.name)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .all()
    )
    names = [x[0] for x in names]
    if new_name in names:
        return False
    category = (
        db.query(RestaurantMenuCategoryDB)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .filter(RestaurantMenuCategoryDB.id == category_id)
        .first()
    )
    if category is not None:
        names = (
            db.query(RestaurantMenuCategoryDB.name)
            .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
            .filter(RestaurantMenuCategoryDB.id != category.id)
            .all()
        )
        names = [x[0] for x in names]
        if new_name in names:
            return False
        category.name = new_name
        db.commit()
        return True
    return False


async def create_menu_item(
    db: Session, restaurant_id: int, item: RestaurantMenuItem, category_id: int
) -> bool:
    category = (
        db.query(RestaurantMenuCategoryDB)
        .filter(RestaurantMenuCategoryDB.restaurant_id == restaurant_id)
        .filter(RestaurantMenuCategoryDB.id == category_id)
        .first()
    )
    if category is None or item.price < 0.10 or item.price > 9999.99:
        return False
    max_order = (
        db.query(func.max(RestaurantMenuItemDB.order))
        .filter(RestaurantMenuItemDB.category.has(restaurant_id == restaurant_id))
        .scalar()
    )
    new_item = RestaurantMenuItemDB(
        category_id=category_id,
        name=item.name,
        order=1 if max_order is None else max_order + 1,
        description=item.description,
        price=item.price,
        status=item.status,
        photo_url=item.photo_url,
    )
    db.add(new_item)
    db.commit()
    return True


async def update_menu_item(
    db: Session, restaurant_id: int, item: RestaurantMenuItem, category_id: int
) -> bool:
    oldItem = (
        db.query(RestaurantMenuItemDB)
        .filter(RestaurantMenuItemDB.id == item.id)
        .filter(RestaurantMenuItemDB.order == item.order)
        .filter(RestaurantMenuItemDB.category_id == category_id)
        .filter(RestaurantMenuItemDB.category.has(restaurant_id == restaurant_id))
        .first()
    )
    if oldItem is None or item.price < 0.10 or item.price > 9999.99:
        return False
    if oldItem.photo_url != item.photo_url and oldItem.photo_url is not None and oldItem.photo_url != "":
        supabase: Client = create_client(
            supabase_url=getEnv().supabase_url, supabase_key=getEnv().supabase_key
        )
        supabase.storage.from_("menuitemspictures").remove(
            [oldItem.photo_url.split("menuitemspictures/")[1]]
        )
    oldItem.name = item.name
    oldItem.description = item.description
    oldItem.price = item.price
    oldItem.status = item.status
    oldItem.photo_url = item.photo_url
    reservations_containing_item =         (db.query(ReservationDB)
        .join(RestaurantDB, RestaurantDB.id == ReservationDB.restaurant_id)
        .filter(
            ReservationDB.status == ReservationStatus.accepted,
        )
        .filter(
            ReservationDB.date
            + func.cast(
                concat(RestaurantDB.reservation_hour_length, " HOURS"), INTERVAL
            )
            >= datetime.now()
        )
        .filter(
            ReservationDB.order.op('->>')(str(oldItem.id)) != None
        )
        .all())
    for reservation in reservations_containing_item:
        if oldItem.status == RestaurantMenuItemType.inactive:
            del reservation.order[str(oldItem.id)]
        else:
            reservation.order[str(oldItem.id)]["name"] = item.name
            reservation.order[str(oldItem.id)]["total_price"] = "{:.2f}".format(item.price*reservation.order[str(oldItem.id)]["count"]).replace('.',',')+" zł"
        flag_modified(reservation,"order")
    db.commit()
    return True


async def update_items_orders(
    db: Session, restaurant_id: int, category_id: int, item_id_1: int, item_id_2: int
) -> bool:
    itemsSelected = (
        db.query(RestaurantMenuItemDB)
        .filter(
            RestaurantMenuItemDB.category_id == category_id,
            RestaurantMenuItemDB.category.has(restaurant_id == restaurant_id),
            RestaurantMenuItemDB.id.in_([item_id_1, item_id_2]),
        )
        .order_by(RestaurantMenuItemDB.order)
        .all()
    )
    if len(itemsSelected) != 2:
        return False
    itemsToChange = (
        db.query(RestaurantMenuItemDB)
        .filter(
            RestaurantMenuItemDB.category_id == category_id,
            RestaurantMenuItemDB.category.has(restaurant_id == restaurant_id),
            RestaurantMenuItemDB.order > itemsSelected[0].order,
            RestaurantMenuItemDB.order < itemsSelected[1].order,
        )
        .all()
    )
    for item in itemsToChange:
        if itemsSelected[0].id == item_id_1:
            item.order = item.order - 1
        else:
            item.order = item.order + 1
    if itemsSelected[0].id == item_id_1:
        itemsSelected[0].order, itemsSelected[1].order = (
            itemsSelected[1].order,
            itemsSelected[1].order - 1,
        )
    else:
        itemsSelected[0].order, itemsSelected[1].order = (
            itemsSelected[0].order + 1,
            itemsSelected[0].order,
        )
    db.commit()
    return True


async def delete_restaurant_item(db: Session, restaurant_id: int, item_id) -> bool:
    item_to_remove = (
        db.query(RestaurantMenuItemDB)
        .filter(RestaurantMenuItemDB.category.has(restaurant_id == restaurant_id))
        .filter(RestaurantMenuItemDB.id == item_id)
        .first()
    )
    if item_to_remove is not None:
        db.delete(item_to_remove)
        db.commit()
        return True
    return False

from models.reservation import ReservationDB, ReservationStatus
from models.restaurant import RestaurantDB