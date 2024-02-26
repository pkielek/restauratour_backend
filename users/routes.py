from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Body, Depends, HTTPException
from config import get_db
from models.menu import (
    RestaurantMenuCategoryUser,
    RestaurantMenuItemType,
    RestaurantMenuItemUser,
    RestaurantMenuUser,
    RestaurantOrderUser,
    get_restaurant_menu_category_items,
    get_restaurant_menu_visible_categories,
)
from models.reservation import (
    AddReservation,
    Reservation,
    cancel_reservation,
    create_reservation,
    does_current_user_have_ongoing_reservations,
    get_current_user_reservations,
    get_current_user_reservations_history,
    get_reservation,
    toggle_needs_service,
    update_reservation_additional_details,
    update_reservation_order,
)
from models.restaurant import (
    RestaurantBase,
    RestaurantInfo,
    RestaurantSearch,
    get_restaurant,
    get_restaurant_flags,
    get_restaurant_hours,
    get_restaurants_by_search,
)
from models.table import (
    PlannerInfo,
    RestaurantBorder,
    RestaurantTable,
    get_free_tables_for_time,
    get_restaurant_borders,
    get_restaurant_free_timeslots_for_day,
    get_restaurant_tables,
)
from models.user import User, update_user_password, validate_password

from security.token import get_current_active_user, get_password_hash
from sqlalchemy.orm import Session

usersRouter = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


@usersRouter.post("/restaurant-search")
async def get_restaurants_by_search_conditions(
    db: Annotated[Session, Depends(get_db)],
    options: Annotated[RestaurantSearch, Body()],
) -> list[RestaurantBase]:
    if not options.is_data_valid():
        raise HTTPException(400, "Nieprawidłowe dane wyszukiwania")
    return await get_restaurants_by_search(db, options)


@usersRouter.get("/restaurant-info")
async def get_restaurant_info(
    restaurant_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> RestaurantInfo:
    restaurantDB = await get_restaurant(db=db, id=restaurant_id)
    if restaurantDB is None:
        raise HTTPException(400, "Błędne zapytanie")
    hours = await get_restaurant_hours(db=db, id=restaurant_id)
    flags = await get_restaurant_flags(db=db, id=restaurant_id)
    restaurant = RestaurantInfo(
        **restaurantDB.to_dict(), opening_hours=hours, flags=flags
    )
    return restaurant


@usersRouter.get("/restaurant-categories")
async def restaurant_menu_categories(
    db: Annotated[Session, Depends(get_db)],
    restaurant_id: int,
) -> RestaurantMenuUser:
    categories = await get_restaurant_menu_visible_categories(
        db=db, restaurant_id=restaurant_id
    )
    items = await get_restaurant_menu_category_items(
        db=db, restaurant_id=restaurant_id, category_id=categories[0].id
    )
    return RestaurantMenuUser(
        categories=[RestaurantMenuCategoryUser(**x.to_dict()) for x in categories],
        items=[
            RestaurantMenuItemUser(
                **x.to_dict(), is_available=x.status == RestaurantMenuItemType.available
            )
            for x in items
        ],
    )


@usersRouter.get("/restaurant-category-items")
async def restaurant_menu_items(
    db: Annotated[Session, Depends(get_db)],
    restaurant_id: int,
    category_id: int,
) -> list[RestaurantMenuItemUser]:
    items = await get_restaurant_menu_category_items(
        db=db, restaurant_id=restaurant_id, category_id=category_id
    )
    return [
        RestaurantMenuItemUser(
            **x.to_dict(), is_available=x.status == RestaurantMenuItemType.available
        )
        for x in items
    ]


@usersRouter.get("/planner-info")
async def get_restaurant_planner_info(
    restaurant_id: int, db: Annotated[Session, Depends(get_db)]
) -> PlannerInfo:
    tables = [
        RestaurantTable(**x.to_dict())
        for x in await get_restaurant_tables(db=db, restaurant_id=restaurant_id)
    ]
    borders = [
        RestaurantBorder(**x.to_dict())
        for x in await get_restaurant_borders(db=db, restaurant_id=restaurant_id)
    ]
    restaurant = await get_restaurant(db=db, id=restaurant_id)
    return PlannerInfo(
        precision=restaurant.plan_precision, tables=tables, borders=borders
    )


@usersRouter.get("/get-date-available-times")
async def get_restaurant_date_available_times(
    restaurant_id: int,
    date: datetime,
    guests_amount: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[datetime]:
    if date.date() < datetime.now().date():
        raise HTTPException(400, "Błędne zapytanie")
    return await get_restaurant_free_timeslots_for_day(
        db, restaurant_id, date.date(), guests_amount
    )


@usersRouter.get("/available-tables-for-time")
async def get_restaurant_time_available_tables(
    db: Annotated[Session, Depends(get_db)],
    restaurant_id: int,
    date: datetime,
    guests_amount: int,
) -> list[str]:
    if date.date() < datetime.now().date():
        raise HTTPException(400, "Błędne zapytanie")
    return [
        x.real_id
        for x in await get_free_tables_for_time(db, restaurant_id, date, guests_amount)
    ]


@usersRouter.post("/reserve-table")
async def reserve_table(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    data: Annotated[AddReservation, Body()],
) -> int:
    if data.date.date() < datetime.now().date():
        raise HTTPException(400, "Błędne zapytanie")
    is_table_free = await get_free_tables_for_time(
        db, data.restaurant_id, data.date, data.guests_amount, data.table
    )
    if len(is_table_free) > 0:
        data.table = is_table_free[0].id
        reservation = await create_reservation(db, data, user.id)
        return reservation.id
    else:
        raise HTTPException(400, "Stolik jest już zajęty w wybranym terminie")


@usersRouter.post("/cancel-reservation")
async def cancel_reservation(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    reservation_id: Annotated[int, Body(embed=True)],
) -> bool:
    result = await cancel_reservation(db, reservation_id, user.id)
    if result:
        return True
    raise HTTPException(
        400,
        "Nie można odwołać wybranej rezerwacji - być może została już usunięta albo odrzucona",
    )

@usersRouter.post("/notify-service")
async def notify_service(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    reservation_id: Annotated[int, Body(embed=True)],
) -> bool:
    result = await toggle_needs_service(db, reservation_id, user.id)
    if result is not False:
        return result.need_service
    raise HTTPException(
        400,
        "Nie można poprosić kelnera - być może rezerwacja została usunięta, odrzucona lub się zakończyła",
    )

@usersRouter.post("/update-reservation-details")
async def update_reservation_details(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    reservation_id: Annotated[int, Body()],
    details: Annotated[str, Body()]
) -> bool:
    if await update_reservation_additional_details(db, user.id, reservation_id, details):
        return True
    raise HTTPException(
        400,
        "Nie można zaktualizować opisu",
    )

@usersRouter.post('/update-order')
async def update_order(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    reservation_id: Annotated[int, Body()],
    order: Annotated[dict[int,int], Body()]
)-> bool:
    result = await update_reservation_order(db, reservation_id, user.id, order)
    if result is not False:
        return True
    raise HTTPException(
        400,
        "Nie można zaktualizować zamówienia",
    )

@usersRouter.get("/current-reservations")
async def current_reservations(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Reservation]:
    return await get_current_user_reservations(db, user.id)

@usersRouter.get('/has-ongoing-reservations')
async def has_ongoing_reservations(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> bool:
    return await does_current_user_have_ongoing_reservations(db, user.id)

@usersRouter.get("/reservation-order-items")
async def reservation_order_items(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    reservation_id: int,
) -> RestaurantOrderUser:
    reservation = await get_reservation(db, reservation_id, user.id)
    if reservation is None:
        raise HTTPException(400, "Wybrana rezerwacja nie istnieje")
    categories = await get_restaurant_menu_visible_categories(
        db=db, restaurant_id=reservation.restaurant_id
    )
    items = await get_restaurant_menu_category_items(
        db=db, restaurant_id=reservation.restaurant_id, category_id=categories[0].id
    )
    
    return RestaurantOrderUser(
        restaurant_id=reservation.restaurant_id,
        current_order={int(k): int(v["count"]) for (k, v) in reservation.order.items()},
        menu=RestaurantMenuUser(
            categories=[RestaurantMenuCategoryUser(**x.to_dict()) for x in categories],
            items=[
                RestaurantMenuItemUser(
                    **x.to_dict(),
                    is_available=x.status == RestaurantMenuItemType.available
                )
                for x in items
            ],
        ),
    )

@usersRouter.get("/reservations-history")
async def reservations_history(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int,
) -> list[Reservation]:
    return await get_current_user_reservations_history(db, user.id, page)


@usersRouter.post("/update-password")
async def update_password(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    new_password: Annotated[str, Body()],
    confirm_password: Annotated[str, Body()],
):
    if not validate_password(new_password):
        raise HTTPException(status_code=400, detail="Hasło nie spełnia wymagań")
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Hasła nie są identyczne")
    await update_user_password(
        db=db, user_id=user.id, hashed_password=get_password_hash(new_password)
    )
    return {"message": "Zapisano zmiany pomyślnie"}
