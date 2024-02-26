from typing import Annotated
from fastapi import APIRouter, Body, Depends, HTTPException, Security
from config import get_db
from models.menu import RestaurantMenuCategoryUser, RestaurantMenuItemType, RestaurantMenuItemUser, RestaurantMenuUser, RestaurantOrderUser, get_restaurant_menu_category_items, get_restaurant_menu_visible_categories
from models.reservation import Reservation, create_waiter_reservation, get_reservation, get_restaurant_current_reservations, get_restaurant_needing_service_reservations_count, get_restaurant_pending_reservations, get_restaurant_pending_reservations_count, get_restaurant_table_coming_reservations_count, get_restaurant_todays_reservations, update_pending_reservation_status, update_reservation_order
from models.restaurant import get_restaurant
from models.table import PlannerInfo, RestaurantBorder, RestaurantTable, get_restaurant_borders, get_restaurant_tables, is_table_free_now
from models.user import Worker, update_worker_password, validate_password
from sqlalchemy.orm import Session


from security.token import get_current_active_user

workersRouter = APIRouter(
    prefix="/api/workers",
    tags=["workers"],
    dependencies=[Security(get_current_active_user, scopes=["worker:basic"])],
    responses={404: {"description": "Not found"}},
)


@workersRouter.get(("/planner-info"))
async def get_restaurant_planner_info(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PlannerInfo:
    tables = [
        RestaurantTable(**x.to_dict())
        for x in await get_restaurant_tables(db=db, restaurant_id=worker.restaurant_id)
    ]
    borders = [
        RestaurantBorder(**x.to_dict())
        for x in await get_restaurant_borders(db=db, restaurant_id=worker.restaurant_id)
    ]
    restaurant = await get_restaurant(db=db, id=worker.restaurant_id)
    return PlannerInfo(
        precision=restaurant.plan_precision, tables=tables, borders=borders
    )

@workersRouter.get("/todays-reservations")
async def todays_reservations(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Reservation]:
    return await get_restaurant_todays_reservations(db, worker.restaurant_id)

@workersRouter.get("/table-coming-reservations")
async def table_coming_reservations(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    table_real_id: str
) -> dict[int,int]:
    return await get_restaurant_table_coming_reservations_count(db, worker.restaurant_id, table_real_id)

@workersRouter.get("/pending-reservations")
async def pending_reservations(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Reservation]:
    return await get_restaurant_pending_reservations(db, worker.restaurant_id)

@workersRouter.get("/pending-reservations-count")
async def pending_reservations_count(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> int:
    return await get_restaurant_pending_reservations_count(db, worker.restaurant_id)

@workersRouter.get("/needing-service-reservations-count")
async def needing_service_reservations_count(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> int:
    return await get_restaurant_needing_service_reservations_count(db, worker.restaurant_id)

@workersRouter.post('/decide-reservation')
async def decide_reservation(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    accept: Annotated[bool, Body()],
    reservation_id: Annotated[int, Body()],
) -> bool:
    result = await update_pending_reservation_status(db, reservation_id, worker.restaurant_id, accept)
    if result is not False:
        return True
    raise HTTPException(
        400,
        "Nie można zaktualizować statusu - został on już zmieniony albo rezerwacja została usunięta",
    )


@workersRouter.get('/current-reservations')
async def current_reservations(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int,
) -> list[Reservation]:
    return await get_restaurant_current_reservations(db, worker.restaurant_id, page)

@workersRouter.get("/restaurant-category-items")
async def restaurant_menu_items(
    db: Annotated[Session, Depends(get_db)],
    worker: Annotated[Worker, Depends(get_current_active_user)],
    category_id: int,
) -> list[RestaurantMenuItemUser]:
    items = await get_restaurant_menu_category_items(
        db=db, restaurant_id=worker.restaurant_id, category_id=category_id
    )
    return [
        RestaurantMenuItemUser(
            **x.to_dict(), is_available=x.status == RestaurantMenuItemType.available
        )
        for x in items
    ]

@workersRouter.get("/reservation-order-items")
async def current_reservations(
    db: Annotated[Session, Depends(get_db)],
    worker: Annotated[Worker, Depends(get_current_active_user)],
    reservation_id: int,
) -> RestaurantOrderUser:
    reservation = await get_reservation(db, reservation_id, None)
    print(reservation)
    if reservation is None or reservation.restaurant_id != worker.restaurant_id:
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

@workersRouter.post('/update-order')
async def update_order(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    reservation_id: Annotated[int, Body()],
    order: Annotated[dict[int,int], Body()]
)-> bool:
    reservation = await get_reservation(db, reservation_id, None)
    if reservation is not None and reservation.restaurant_id == worker.restaurant_id:
        result = await update_reservation_order(db, reservation_id, None, order)
        if result is not False:
            return True
    raise HTTPException(
        400,
        "Nie można zaktualizować zamówienia",
    )

@workersRouter.post("/reserve-table")
async def reserve_table(
    worker: Annotated[Worker, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    table_id: Annotated[str, Body(embed=True)]
) -> int:
    table = await is_table_free_now(
        db, worker.restaurant_id, table_id
    )
    if table is not None:
        return (await create_waiter_reservation(db,worker,table.id)).id
    else:
        raise HTTPException(400, "Stolik jest już zajęty w wybranym terminie")