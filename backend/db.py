from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from sqlmodel import Field, SQLModel
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.future import select
from sqlite3 import Connection


class UserBase(SQLModel):
    username: str
    password: str


class UserCreate(UserBase):
    pass


class User(UserBase, table=True):
    id: int = Field(primary_key=True)


class DocumentBase(SQLModel):
    content: str


class Document(DocumentBase, table=True):
    id: int = Field(primary_key=True)


sqlite_file_name = "sharenotes.db"
sqlite_url = f"sqlite+aiosqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_async_engine(sqlite_url, echo=True, connect_args=connect_args)
SessionMaker = async_sessionmaker(autocommit=False, bind=engine)


@asynccontextmanager
async def connect():
    async with engine.begin() as conn:
        try:
            yield conn
        except:
            conn.rollback()
            raise


async def session() -> AsyncGenerator[AsyncSession, Any]:
    async with SessionMaker() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise


async def read_users(s: AsyncSession):
    res = await s.execute(select(User))
    users = res.scalars().all()
    return users


async def create_user(s: AsyncSession, uc: UserCreate):
    user = User(**uc.model_dump(exclude_unset=True))
    s.add(user)
    await s.commit()
    await s.refresh(user)
    return user


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: Connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def create_all():
    async with connect() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
