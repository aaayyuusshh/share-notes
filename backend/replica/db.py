from __future__ import annotations
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional
import logging
from sqlmodel import Field, SQLModel
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.future import select
from sqlite3 import Connection
from exceptions import HTTPException
#from settings import settings
from pathlib import Path
import os

class DocumentBase(SQLModel):
    name: str
    content: str


class DocumentList(SQLModel):
    id: int
    name: str


class Document(DocumentBase, table=True):
    id: int = Field(primary_key=True)


class DocumentUpdate(DocumentBase):
    id: int
    content: Optional[str]


# NOTE: Remove this later for me the settings file does not work so I got the enviroment variable instead
MY_PORT = os.getenv('PORT')

REPLICA_DIR = Path(__file__).parent.resolve() / "dbs"

if not REPLICA_DIR.is_dir():
    REPLICA_DIR.mkdir()

sqlite_path = REPLICA_DIR / f"sharenotes_{MY_PORT}.db"
sqlite_url = f"sqlite+aiosqlite:///{sqlite_path}"

connect_args = {"check_same_thread": False}
engine = create_async_engine(sqlite_url, echo=True, connect_args=connect_args)
SessionMaker = async_sessionmaker(autocommit=False, bind=engine)

logger = logging.getLogger("uvicorn")


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


async def read_document(s: AsyncSession, document_id: int):
    doc = await s.get(Document, document_id)
    return doc


async def create_document(s: AsyncSession, docName: str):
    doc = Document(name=docName, content="")
    s.add(doc)
    await s.commit()
    await s.refresh(doc)
    return doc.id

async def create_repl_document(s: AsyncSession, docName: str, docId: int):
    doc = Document(id=docId, name=docName, content="")
    s.add(doc)
    await s.commit()
    await s.refresh(doc)


async def create_document_with_content(s: AsyncSession, docName: str, docContent: str):
    doc = Document(name=docName, content=docContent)
    s.add(doc)
    await s.commit()
    await s.refresh(doc)
    return doc


# Causes errors
async def doc_list_db():
    async with SessionMaker() as s:
        doc_list = await s.execute(select(Document.id))
    return doc_list


async def update_document(s: AsyncSession, du: DocumentUpdate):
    doc = await read_document(s, du.id)
    logger.info("Document before update")
    logger.info(doc)
    if not doc:
        raise HTTPException(404, f"document ID: {du.id} not found")
    if du.content:
        doc.content = du.content
    await s.commit()
    await s.refresh(doc)
    doc = await read_document(s, du.id)
    logger.info("Document after update")
    logger.info(doc)
    return doc


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: Connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def create_all():
    async with connect() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


"""
class UserBase(SQLModel):
    username: str
    password: str


class UserCreate(UserBase):
    pass


class User(UserBase, table=True):
    id: int = Field(primary_key=True)


async def read_users(s: AsyncSession):
    res = await s.execute(select(User))
    users = res.scalars().all()
    return users


async def create_user(s: AsyncSession, uc: UserCreate):
    user = User(**uc.model_dump(exclude_unset=True))
    s.add(user)
    await s.commit()
    return user
"""
