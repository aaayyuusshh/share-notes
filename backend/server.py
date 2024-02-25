from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from db import (
    DocumentUpdate,
    UserCreate,
    create_all,
    AsyncSession,
    create_document,
    read_document,
    read_users,
    session,
    User,
    create_user,
    update_document,
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


html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <content id='document'>
        </content>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws/1");
            var input = document.getElementById("messageText");
            ws.onmessage = function(event) {
                var doc = document.getElementById('document');
                doc.textContent = event.data;
                input.value = event.data;
            };
            function sendMessage(event) {
                ws.send(input.value);
                event.preventDefault();
            }
        </script>
    </body>
</html>
"""


@app.get("/")
async def get():
    return HTMLResponse(html)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


@app.websocket("/ws/{document_id}")
async def websocket_endpoint(websocket: WebSocket, document_id: int, s: Session):
    await manager.connect(websocket)

    doc = await read_document(s, document_id)
    if not doc:
        doc = await create_document(s, document_id)

    await websocket.send_text(doc.content)

    try:
        while True:
            data = await websocket.receive_text()
            doc = await update_document(s, DocumentUpdate(content=data, id=document_id))
            await manager.broadcast(doc.content)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
