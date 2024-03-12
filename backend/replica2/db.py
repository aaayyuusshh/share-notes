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


sqlite_file_name = "sharenotes.db"
sqlite_url = f"sqlite+aiosqlite:///{sqlite_file_name}"

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
    logger.info("DB")
    logger.info(document_id)
    doc = await s.get(Document, document_id)
    logger.info(doc)
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
async def doc_list(s: AsyncSession):
    q = select(Document.id, Document.name)
    doc_list = await s.execute(q)
    return doc_list


async def update_document(s: AsyncSession, du: DocumentUpdate):
    doc = await read_document(s, du.id)
    logger.info(doc)
    logger.info(doc.content)
    if not doc:
        raise HTTPException(404, f"document ID: {du.id} not found")
    if du.content:
        doc.content = du.content
    await s.commit()
    await s.refresh(doc)
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
