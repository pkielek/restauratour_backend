from datetime import datetime, timedelta

from models.user import Worker
from security.token import pwd_context

def worker_activation_link_template(worker: Worker, date : datetime = datetime.now()):
    return worker.email + '!' + worker.surname + '#' + worker.first_name + '$' + str(worker.restaurant.id) + '%' + date.strftime('%Y-%m-%d-%H')

def get_worker_activation_link(worker: Worker) -> str:
    return pwd_context.hash(worker_activation_link_template(worker))

def verify_worker_activation_link(worker: Worker, token: str) -> str:
    date = datetime.now()
    delta = timedelta(hours=-1)
    i = 0
    while i < 48:
        if pwd_context.verify(worker_activation_link_template(worker,date),token):
            return True
        i+=1
        date += delta
    return False