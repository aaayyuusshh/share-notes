from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import Depends, FastAPI

from db import (
    UserCreate,
    create_all,
    AsyncSession,
    read_users,
    session,
    User,
    create_user,
)

Session = Annotated[AsyncSession, Depends(session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/users/")
async def get_users(s: Session) -> list[User]:
    return await read_users(s)


@app.post("/users/")
async def post_user(s: Session, uc: UserCreate) -> User:
    return await create_user(s, uc)
