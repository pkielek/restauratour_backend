from datetime import datetime, timedelta

from models.user import User
from security.token import pwd_context

def user_activation_link_template(user: User, date : datetime = datetime.now()):
    return user.email + '!' + user.first_name + '%' + date.strftime('%Y-%m-%d-%H')

def get_user_activation_link(user: User) -> str:
    return pwd_context.hash(user_activation_link_template(user))

def verify_user_activation_link(user: User, token: str) -> str:
    date = datetime.now()
    delta = timedelta(hours=-1)
    i = 0
    while i < 48:
        if pwd_context.verify(user_activation_link_template(user,date),token):
            return True
        i+=1
        date += delta
    return False