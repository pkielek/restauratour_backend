from fastapi_mail import FastMail, MessageSchema, MessageType
from config import mail_conf
from models.user import User, UserDB, WorkerDB
from security.users import get_user_activation_link

from security.workers import get_worker_activation_link

async def send_activation_mail_to_worker(worker: WorkerDB):
    token = get_worker_activation_link(worker)
    html = f"""<h1>Cześć {worker.first_name},</h1>
    <p>Właśnie założone zostało Twoje konto kelnera w aplikacji Restaura TOUR. By ustanowić swoje hasło do konta, ściągnij aplikację i w zakładce "Ustaw nowe hasło" użyj swojego e-maila i poniższego klucza:<br>
    Klucz do ustanowienia nowego hasła: <strong>{token}</strong><br>
    <br>
    <p>W razie problemów skontaktuj się ze swoim pracodawcą<br>
    <br>
    Życzymy powodzenia i przyjemnej pracy!<br>
    Zespół Restaura TOUR</p>"""

    message = MessageSchema(
        subject="Konto w aplikacji Restaura TOUR",
        recipients=[worker.email],
        body=html,
        subtype=MessageType.html)

    fm = FastMail(mail_conf)
    await fm.send_message(message)
    return True

async def send_password_reset_mail_to_worker(worker: WorkerDB):
    token = get_worker_activation_link(worker)
    html = f"""<h1>Cześć {worker.first_name},</h1>
    <p>Właśnie otrzymaliśmy prośbę o zresetowanie hasła w aplikacji Restaura TOUR. By ustanowić nowe hasło do konta, w aplikacji Restaura TOUR w zakładce "Ustaw nowe hasło" użyj swojego e-maila i poniższego klucza:<br>
    Klucz do ustanowienia nowego hasła: <strong>{token}</strong><br>
    <br>
    <p>W razie problemów skontaktuj się ze swoim pracodawcą<br>
    <br>
    Zespół Restaura TOUR</p>"""

    message = MessageSchema(
        subject="Zresetowanie hasła -  Restaura TOUR",
        recipients=[worker.email],
        body=html,
        subtype=MessageType.html)

    fm = FastMail(mail_conf)
    await fm.send_message(message)
    return True

async def send_activation_link_mail_to_user(user: UserDB):
    token = get_user_activation_link(user)
    html = f"""<h1>Cześć {user.first_name},</h1>
    <p>Właśnie zarejestrowałeś swoje konto w Restaura TOUR. By je aktywować, kliknij w poniższy link: <br>
    <strong><a href="https://sample-pjj3vhv3la-ew.a.run.app/api/users/activate?token={token}&email={user.email}">Link</a></strong><br>
    <br>
    Zespół Restaura TOUR</p>"""

    message = MessageSchema(
        subject="Aktywacja konta -  Restaura TOUR",
        recipients=[user.email],
        body=html,
        subtype=MessageType.html)

    fm = FastMail(mail_conf)
    await fm.send_message(message)
    return True