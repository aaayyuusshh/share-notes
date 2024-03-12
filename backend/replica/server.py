from contextlib import asynccontextmanager
from typing import Annotated, List, Any
from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from sqlalchemy.future import select
import os
from db import (
    DocumentUpdate,
    Document,
    DocumentList,
    create_all,
    AsyncSession,
    create_document,
    create_document_with_content,
    read_document,
    session,
    update_document,
    create_repl_document
)
import websockets


Session = Annotated[AsyncSession, Depends(session)]

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield

app = FastAPI(lifespan=lifespan)
MY_PORT = os.getenv('PORT')
print(MY_PORT)


origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

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

logger = logging.getLogger("uvicorn")


@app.post("/newDocID/{docName}")
async def create_docID(s: Session, docName: str):
    docID = await create_document(s, docName)
    # hard coded passing of the port number, should be done in master
    return {"docID": docID, "port": 8001}


@app.post("/createDoc/", response_model=Document)
async def create_doc(docName: str, docContent: str, s: Session):
    doc = await create_document_with_content(s, docName, docContent)
    return doc


@app.get("/docList/", response_model=List[DocumentList])
async def doc_list(s: Session) -> Any:
    #docList = await doc_list(s)
    docList = await s.execute(select(Document.id, Document.name))
    return docList



@app.websocket("/ws/{document_id}/{docName}")
async def websocket_endpoint(websocket: WebSocket, document_id: int, docName: str, s: Session):
    print("My port is: ", MY_PORT)
    logger.info("running")
    await manager.connect(websocket)

    logger.info(document_id)
    logger.info(docName)
    doc = await read_document(s, document_id)

    # shouldn't happen
    if not doc:
        logger.info("Document had to be created, something went wrong")
        doc = await create_document(s, document_id)

    await websocket.send_text(doc.content)

    try:
        while True:
            data = await websocket.receive_text()
            # parse data json
            data = json.loads(data)['content']
            logger.info("Content: ")
            logger.info(data)
            doc = await update_document(s, DocumentUpdate(content=data, id=document_id, name=docName))
            await manager.broadcast(doc.content)

            for port in range(8001, 8006):
                if port == MY_PORT:
                    continue
                response = await connect_to_replica(document_id, docName, doc.content, port)


    except WebSocketDisconnect:
        manager.disconnect(websocket)

# create websocket to connect to replica
async def connect_to_replica(document_id: int, docName: str, content: str, port: int):
    uri = f"ws://localhost:{port}/replica/ws/{document_id}/{docName}"
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected to replica {uri}")
            await websocket.send(json.dumps({
                "content": content
            }))
            response = await websocket.recv()
            print(response, f", {MY_PORT}")
            return response
    except ConnectionRefusedError:
        print(f"Failed to connect to {uri}. Connection refused.")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise



@app.websocket("/replica/ws/{document_id}/{docName}")
async def replica_websocket_endpoint(websocket: WebSocket, document_id: int, docName: str, s: Session):
    await manager.connect(websocket)
    print(f"Connected to document {document_id} with name {docName}")

    doc = await read_document(s, document_id)

    # shouldn't happen
    if not doc:
        logger.info("Document had to be created, something went wrong")
        await create_repl_document(s, docName, document_id)

    try:
        while True:
            data = await websocket.receive_text()
            print(docName)
            print(data)
            # parse data json
            data = json.loads(data)['content']

            doc = await update_document(s, DocumentUpdate(content=data, id=document_id, name=docName))
            print(f"{MY_PORT}")
            await websocket.send_text(f"ack from replica {MY_PORT}")
    except WebSocketDisconnect:
        print(f"Connection closed with exception")

"""
@app.get("/users/")
async def get_users(s: Session) -> list[User]:
    return await read_users(s)


@app.post("/users/")
async def post_user(s: Session, uc: UserCreate) -> User:
    return await create_user(s, uc)
"""