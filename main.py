from fastapi import FastAPI
from owners.routes import ownersRouter
from workers.routes import workersRouter
from users.routes import usersRouter
from security.login import loginRouter
from config import Base, DBEngine
from fastapi.middleware.cors import CORSMiddleware
origins = [
    "*",
]


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(ownersRouter)
app.include_router(workersRouter)
app.include_router(usersRouter)
app.include_router(loginRouter)