from fastapi_mail import ConnectionConfig
from pydantic_settings import BaseSettings
from pydantic import EmailStr, PostgresDsn
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase

# CONFIG
class Env(BaseSettings):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    sqlalchemy_database_url: PostgresDsn
    supabase_url: str
    supabase_key: str
    google_oauth_client: str
    google_oauth_secret: str
    mail_username: str
    mail_password: str
    mail_from: EmailStr
    mail_server: str
    mail_from_name :str

    class Config:
        env_file = "envfile"

@lru_cache
def getEnv():
    return Env()

# DATABASE 
DBEngine = create_engine(getEnv().sqlalchemy_database_url.unicode_string(),pool_pre_ping=True)
DBSession = sessionmaker(autocommit = False, autoflush = False, bind = DBEngine)

class Base(DeclarativeBase):
    pass
    def to_dict(self):
        return {field.name:getattr(self, field.name) for field in self.__table__.c}

def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        db.close()

# MAILING

mail_conf = conf = ConnectionConfig(
    MAIL_USERNAME = getEnv().mail_username,
    MAIL_PASSWORD = getEnv().mail_password,
    MAIL_PORT = 465,
    MAIL_SERVER = getEnv().mail_server,
    MAIL_FROM = getEnv().mail_from,
    MAIL_FROM_NAME = getEnv().mail_from_name,
    MAIL_STARTTLS = False,
    MAIL_SSL_TLS = True,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)