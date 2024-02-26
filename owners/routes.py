from typing import Annotated
import uuid
from fastapi import APIRouter, Body, Depends, File, HTTPException, Security, UploadFile
from config import get_db, getEnv
from mailing import send_activation_mail_to_worker, send_password_reset_mail_to_worker
from models.menu import (
    RestaurantMenuCategoryDB,
    RestaurantMenuCategory,
    RestaurantMenuFull,
    RestaurantMenuItem,
    add_new_category,
    create_menu_item,
    delete_restaurant_category,
    delete_restaurant_item,
    get_restaurant_menu,
    update_categories_orders,
    update_category_name,
    update_category_visibility,
    update_items_orders,
    update_menu_item,
)
from models.restaurant import (
    RestaurantInfo,
    UpdateRestaurantInfo,
    get_restaurant,
    get_restaurant_flags,
    get_restaurant_hours,
    get_restaurant_photo,
    update_precision,
    update_restaurant_contact,
    update_restaurant_flags,
    update_restaurant_opening_hours,
    update_restaurant_photo,
    update_restaurant_reservation_length,
)
from models.table import (
    PlannerInfo,
    RestaurantBorder,
    RestaurantTable,
    get_restaurant_borders,
    get_restaurant_tables,
    update_borders,
    update_tables,
)
from models.user import (
    AccountStatus,
    CreateWorker,
    CreateWorkerDB,
    Owner,
    UserType,
    WorkerListItem,
    get_restaurant_workers,
    get_user,
    get_user_by_email,
    insert_worker,
    restore_deleted_worker,
    update_worker_password,
    update_worker_status,
    validate_password,
)

from sqlalchemy.orm import Session
from security.token import get_current_active_user, get_password_hash
from supabase import create_client, Client
from hashlib import sha256

ownersRouter = APIRouter(
    prefix="/api/owners",
    tags=["owners"],
    dependencies=[Security(get_current_active_user, scopes=["owner:basic"])],
    responses={404: {"description": "Błąd aplikacji"}},
)


@ownersRouter.post("/create-worker")
async def create_worker(
    worker: CreateWorker,
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    worker_dict = worker.model_dump()
    user = await get_user_by_email(db=db, type=UserType.worker, email=worker.email)
    if user and user.status != AccountStatus.deleted:
        raise HTTPException(
            status_code=400, detail="Konto kelnera o takim e-mailu już istnieje"
        )
    if user:
        worker_created = await restore_deleted_worker(
            db=db, worker=user, worker_data=worker
        )
    else:
        worker_create = CreateWorkerDB(**worker_dict, restaurant=owner.restaurant_id)
        worker_created = await insert_worker(db=db, worker=worker_create)
    mail_status = await send_activation_mail_to_worker(worker_created)
    if mail_status:
        return {
            "message": "Konto użytkownika utworzono prawidłowo. Hasło będzie mógł on ustawić przy pomocy klucz wysłanego w wiadomości mailowej",
            "status": "success",
        }
    raise HTTPException(
        status_code=400, detail="Konto kelnera o takim e-mailu już istnieje"
    )


@ownersRouter.post("/resend-worker-activation-link")
async def resend_worker_activation_link(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    worker_id: Annotated[int, Body(embed=True)],
):
    worker = await get_user(db, worker_id, UserType.worker)
    if owner.restaurant_id != worker.restaurant_id:
        raise HTTPException(status_code=401, detail="Błąd autoryzacji!")
    if worker.status == AccountStatus.deleted:
        raise HTTPException(status_code=400, detail="Wybrane konto nie istnieje")
    if worker.status == AccountStatus.blocked:
        raise HTTPException(
            status_code=400,
            detail="Przed zresetowaniem hasła kelnerowi odblokuj jego konto",
        )
    if worker.status == AccountStatus.active:
        await send_password_reset_mail_to_worker(worker)
        return {
            "message": "Klucz do zresetowania hasła został wysłany do kelnera w wiadomości mailowej."
        }
    elif worker.status == AccountStatus.disabled:
        await send_activation_mail_to_worker(worker)
        return {
            "message": "Klucz do aktywacji konta został wysłany do kelnera w wiadomości mailowej."
        }


@ownersRouter.post("/workers-list")
async def workers_list(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[WorkerListItem]:
    return await get_restaurant_workers(db=db, restaurant_id=owner.restaurant_id)


@ownersRouter.post("/remove-worker")
async def remove_worker(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    worker_id: Annotated[int, Body(embed=True)],
):
    worker = await get_user(db, worker_id, UserType.worker)
    if owner.restaurant_id != worker.restaurant_id:
        raise HTTPException(status_code=401, detail="Błąd autoryzacji!")
    if worker.status == AccountStatus.deleted:
        raise HTTPException(status_code=400, detail="Wybrane konto nie istnieje")
    await update_worker_status(db=db, worker_id=worker_id, status=AccountStatus.deleted)
    return {"message": "Usunięto kelnera pomyślnie"}


@ownersRouter.post("/enable-worker")
async def enable_worker(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    worker_id: Annotated[int, Body(embed=True)],
):
    worker = await get_user(db, worker_id, UserType.worker)
    if owner.restaurant_id != worker.restaurant_id:
        raise HTTPException(status_code=401, detail="Błąd autoryzacji!")
    if worker.status == AccountStatus.active:
        raise HTTPException(status_code=400, detail="Wybrane konto jest już aktywne")
    if worker.status == AccountStatus.deleted:
        raise HTTPException(status_code=400, detail="Wybrane konto nie istnieje")
    if worker.status == AccountStatus.disabled:
        raise HTTPException(
            status_code=400, detail="Wybrane konto nie zostało wcześniej aktywowane"
        )
    await update_worker_status(db=db, worker_id=worker_id, status=AccountStatus.active)
    return {"message": "Odblokowano kelnera pomyślnie"}


@ownersRouter.post("/disable-worker")
async def disable_worker(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    worker_id: Annotated[int, Body(embed=True)],
):
    worker = await get_user(db, worker_id, UserType.worker)
    if owner.restaurant_id != worker.restaurant_id:
        raise HTTPException(status_code=401, detail="Błąd autoryzacji!")
    if worker.status == AccountStatus.blocked:
        raise HTTPException(
            status_code=400, detail="Wybrane konto jest już zablokowane"
        )
    if worker.status == AccountStatus.deleted:
        raise HTTPException(status_code=400, detail="Wybrane konto nie istnieje")
    if worker.status == AccountStatus.disabled:
        raise HTTPException(
            status_code=400, detail="Wybrane konto nie zostało wcześniej aktywowane"
        )
    await update_worker_status(db=db, worker_id=worker_id, status=AccountStatus.blocked)
    return {"message": "Zablokowano kelnera pomyślnie"}


@ownersRouter.get("/restaurant-info")
async def get_restaurant_info(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RestaurantInfo:
    restaurantDB = await get_restaurant(db=db, id=owner.restaurant_id)
    hours = await get_restaurant_hours(db=db, id=owner.restaurant_id)
    flags = await get_restaurant_flags(db=db, id=owner.restaurant_id)
    restaurant = RestaurantInfo(
        **restaurantDB.to_dict(), opening_hours=hours, flags=flags
    )
    return restaurant


@ownersRouter.get(("/planner-info"))
async def get_restaurant_planner_info(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PlannerInfo:
    tables = [
        RestaurantTable(**x.to_dict())
        for x in await get_restaurant_tables(db=db, restaurant_id=owner.restaurant_id)
    ]
    borders = [
        RestaurantBorder(**x.to_dict())
        for x in await get_restaurant_borders(db=db, restaurant_id=owner.restaurant_id)
    ]
    restaurant = await get_restaurant(db=db, id=owner.restaurant_id)
    return PlannerInfo(
        precision=restaurant.plan_precision, tables=tables, borders=borders
    )


@ownersRouter.post("/save-precision")
async def save_precision(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    precision: Annotated[int, Body(embed=True)],
):
    if precision < 15 or precision > 50:
        raise HTTPException(status_code=400, detail="Błędna wartość precyzji")
    await update_precision(
        db=db, restaurant_id=owner.restaurant_id, precision=precision
    )
    return {"message": "Zapisano precyzję pomyślnie"}


@ownersRouter.post("/save-planner-info")
async def save_planner_info(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    info: Annotated[PlannerInfo, Body()],
):
    errors = info.isDataValid()
    if len(errors) == 0:
        await update_precision(
            db=db, restaurant_id=owner.restaurant_id, precision=info.precision
        )
        await update_tables(
            db=db, restaurant_id=owner.restaurant_id, newTables=info.tables
        )
        await update_borders(
            db=db, restaurant_id=owner.restaurant_id, newBorders=info.borders
        )
        return {"message": "Zapisano zmiany pomyślnie"}
    raise HTTPException(status_code=400, detail=list(errors))


@ownersRouter.post("/save-restaurant-info")
async def save_restaurant_info(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    info: Annotated[UpdateRestaurantInfo, Body()],
):
    error = info.isDataValid()
    if error != "":
        raise HTTPException(status_code=400, detail=error)
    await update_restaurant_contact(
        db=db,
        restaurant_id=owner.restaurant_id,
        phone_number=info.phone_number,
        email=info.email,
    )
    await update_restaurant_reservation_length(db=db,restaurant_id=owner.restaurant_id,value = info.reservation_hour_length)
    await update_restaurant_flags(
        db=db, restaurant_id=owner.restaurant_id, flags=info.flags
    )
    await update_restaurant_opening_hours(
        db=db, restaurant_id=owner.restaurant_id, opening_hours=info.opening_hours
    )
    return {"message": "Zapisano zmiany pomyślnie"}


@ownersRouter.get("/restaurant-menu")
async def restaurant_menu(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RestaurantMenuFull:
    return RestaurantMenuFull(
        menu=[RestaurantMenuCategory(**x.to_dict(),items=[RestaurantMenuItem(**y.to_dict()) for y in x.items])
        for x in await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)],
        photo_url=await get_restaurant_photo(db=db, restaurant_id=owner.restaurant_id),
    )


@ownersRouter.post("/add-category")
async def add_category(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[RestaurantMenuCategory]:
    await add_new_category(db=db, restaurant_id=owner.restaurant_id)
    return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)


@ownersRouter.post("/delete-category")
async def delete_category(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    category_id: Annotated[int, Body(embed=True)],
) -> list[RestaurantMenuCategory]:
    result = await delete_restaurant_category(
        db=db, restaurant_id=owner.restaurant_id, category_id=category_id
    )
    if result:
        return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)
    raise HTTPException(status_code=400, detail="Kategoria nie istnieje")


@ownersRouter.post("/switch-category-visibility")
async def switch_category_visibility(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    category_id: Annotated[int, Body(embed=True)],
) -> list[RestaurantMenuCategory]:
    result = await update_category_visibility(
        db=db, restaurant_id=owner.restaurant_id, category_id=category_id
    )
    if result:
        return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)
    raise HTTPException(status_code=400, detail="Kategoria nie istnieje")


@ownersRouter.post("/swap-categories-orders")
async def swap_categories_orders(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    category_id_1: Annotated[int, Body()],
    category_id_2: Annotated[int, Body()],
) -> list[RestaurantMenuCategory]:
    result = await update_categories_orders(
        db=db,
        restaurant_id=owner.restaurant_id,
        category_id_1=category_id_1,
        category_id_2=category_id_2,
    )
    if result:
        return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)
    raise HTTPException(status_code=400, detail="Błąd zmiany kolejności kategorii")


@ownersRouter.post("/update-category-name")
async def update_restaurant_category_name(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    category_id: Annotated[int, Body()],
    new_value: Annotated[str, Body()],
) -> list[RestaurantMenuCategory]:
    result = await update_category_name(
        db=db,
        restaurant_id=owner.restaurant_id,
        category_id=category_id,
        new_name=new_value,
    )
    if result:
        return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)
    raise HTTPException(
        status_code=400,
        detail="Kategoria nie istnieje lub istnieje inna kategoria o tej samej nazwie",
    )


@ownersRouter.post("/update-password")
async def update_restaurant_category_name(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    new_password: Annotated[str, Body()],
    confirm_password: Annotated[str, Body()],
):
    if not validate_password(new_password):
        raise HTTPException(status_code=400, detail="Hasło nie spełnia wymagań")
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Hasła nie są identyczne")
    await update_worker_password(
        db=db, worker_id=owner.id, hashed_password=get_password_hash(new_password)
    )
    return {"message": "Zapisano zmiany pomyślnie"}


@ownersRouter.post("/upload-restaurant-photo")
async def upload_restaurant_photo(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile,
) -> str:
    name = uuid.uuid4().hex + ".png"
    bytes = await file.read()
    supabase: Client = create_client(
        supabase_url=getEnv().supabase_url, supabase_key=getEnv().supabase_key
    )
    bucket = supabase.storage.from_("menuitemspictures")

    bucket.upload(
        file=bytes,
        path="restaurant_pictures/" + name,
        file_options={"content-type": "image/png"},
    )
    photo_url = bucket.get_public_url("restaurant_pictures/" + name).split("?")[0]
    old_photo_url = await update_restaurant_photo(
        db=db, restaurant_id=owner.restaurant_id, photo_url=photo_url
    )
    if len(old_photo_url) > 0:
        bucket.remove([old_photo_url.split("menuitemspictures/")[1]])
    return photo_url

@ownersRouter.post('/upload-item-photo')
async def upload_item_photo( 
    owner: Annotated[Owner, Depends(get_current_active_user)],
    file: UploadFile,
)-> str:
    name = uuid.uuid4().hex + ".png"
    bytes = await file.read()
    restaurant_name_hash = sha256(owner.restaurant.name.encode()).hexdigest()

    supabase: Client = create_client(
        supabase_url=getEnv().supabase_url, supabase_key=getEnv().supabase_key
    )
    bucket = supabase.storage.from_("menuitemspictures")

    bucket.upload(
        file=bytes,
        path="restaurant_pictures/" + restaurant_name_hash + "/" + name,
        file_options={"content-type": "image/png"},
    )
    photo_url = bucket.get_public_url("restaurant_pictures/" + restaurant_name_hash + "/" + name).split("?")[0]
    return photo_url

@ownersRouter.post('/delete-uploaded-photo')
async def delete_uploaded_photo( 
    owner: Annotated[Owner, Depends(get_current_active_user)],
    url: Annotated[str, Body(embed=True)],
) -> bool:
    if sha256(owner.restaurant.name.encode()).hexdigest() not in url:
        raise HTTPException(status_code=400, detail="Nie masz dostępu do tego zasobu")
    supabase: Client = create_client(
        supabase_url=getEnv().supabase_url, supabase_key=getEnv().supabase_key
    )
    supabase.storage.from_("menuitemspictures").remove([url.split("menuitemspictures/")[1]])
    return True

@ownersRouter.post('/update-item')
async def update_item(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    item: Annotated[RestaurantMenuItem, Body()],
    category_id: Annotated[int,Body()]
)-> list[RestaurantMenuCategory]:
    if item.id==-1 or item.order == -1:
        result = await create_menu_item(db=db,restaurant_id=owner.restaurant_id, item=item,category_id=category_id)
    else:
        result = await update_menu_item(db=db,restaurant_id=owner.restaurant_id, item=item, category_id = category_id)
    if not result:
        raise HTTPException(status_code=400, detail="Błąd zapisu pozycji")
    return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)

@ownersRouter.post("/swap-items-orders")
async def swap_items_orders(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    item_id_1: Annotated[int, Body()],
    item_id_2: Annotated[int, Body()],
    category_id: Annotated[int, Body()]
) -> list[RestaurantMenuCategory]:
    result = await update_items_orders(
        db=db,
        restaurant_id=owner.restaurant_id,
        item_id_1=item_id_1,
        item_id_2=item_id_2,
        category_id=category_id
    )
    if result:
        return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)
    raise HTTPException(status_code=400, detail="Błąd zmiany kolejności pozycji")

@ownersRouter.post("/delete-item")
async def delete_category(
    owner: Annotated[Owner, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    item_id: Annotated[int, Body(embed=True)],
) -> list[RestaurantMenuCategory]:
    result = await delete_restaurant_item(
        db=db, restaurant_id=owner.restaurant_id, item_id=item_id
    )
    if result:
        return await get_restaurant_menu(db=db, restaurant_id=owner.restaurant_id)
    raise HTTPException(status_code=400, detail="Pozycja nie istnieje lub ma aktualne zamówienia - ustaw jej status na nieaktywny")