from contextlib import asynccontextmanager
from typing import Annotated, List, Any, Tuple, Dict
from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
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
    create_repl_document,
    doc_list_db
)
import websockets
import requests
import time
import asyncio
from collections import defaultdict

# alternative to directly defining paramter type
from pydantic import BaseModel

class Server(BaseModel):
    IP: str
    port: str

Session = Annotated[AsyncSession, Depends(session)]

logger = logging.getLogger("uvicorn")

# GLOBAL ARRAYS/QUEUES
server_list = []
successor = 0
doc_queues: dict[int, list] = {}
doc_permission: dict[WebSocket, bool] = {}

MY_PORT = os.getenv("PORT")
logger.info(MY_PORT)

MY_IP = os.getenv("IP")
logger.info(MY_IP)

MASTER_IP = os.getenv("MASTER_IP")
logger.info(MASTER_IP)

# TODO: DEAL with creation of documents when a replica has crashed (right now the master waits forever)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    # Initailize variables for synchronization
    await create_doc_queues()
    # inform master that you want to be registered to the cluster
    reply = requests.post(f"http://{MASTER_IP}:8000/addServer/", params={"IP": MY_IP, "port": MY_PORT})
    logger.info(reply)
    yield

app = FastAPI(lifespan=lifespan)

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
        self.active_connections: dict[int, list] = {}

    async def connect(self, docID: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(docID, []).append(websocket)

    def disconnect(self, docID: int, websocket: WebSocket):
        self.active_connections[docID].remove(websocket)

    async def broadcast(self, docID: int, message: str):
        if docID in self.active_connections:
            for connection in self.active_connections[docID]:
                await connection.send_text(message)

manager = ConnectionManager()


# Function for populating queues for each document
async def create_doc_queues():
    docList = await doc_list_db()
    for doc in docList:
        logger.info(doc[0])
        doc_queues[int(doc[0])] = []


@app.post("/newDocID/{docName}/")
async def create_docID(s: Session, docName: str):
    docID = await create_document(s, docName)
    doc_queues[docID] = [] # create queue for docID
    return {"docID": docID}


@app.get("/docList/", response_model=List[DocumentList])
async def doc_list(s: Session) -> Any:
    docList = await s.execute(select(Document.id, Document.name))
    return docList


# Updating server list to reflect any changes in the master
# TODO: type should be List[Tuple[str, str]] to prevent the need for using split ... but causes errors for some reason
@app.post("/updateServerList/")
async def update_server_list(new_server_list: list[str]):
    global server_list
    global successor
    server_list = new_server_list
    index = server_list.index(f"{MY_IP}:{MY_PORT}")
    successor = (index+1) % len(server_list)
    logger.info(server_list)
    logger.info("Index of successor: ")
    logger.info(successor)

    return {"message": "Server list updated successfully"}


# For every document in its documement list, create a token and send it to its successor
@app.post("/initializeTokens/")
async def initialize_tokens(s: Session):
    logger.info("INITIALIZE TOKENS (ALL)")
    docList = await s.execute(select(Document.id, Document.name))
    logger.info(docList)
    for doc in docList:
        print("doc", doc[0])
        send_token(doc[0])


# Create a token ONLY for the specified docID
@app.post("/initializeToken/{docID}/")
async def initialize_token(docID: int):
    logger.info("INITIALIZE TOKEN (ONE)")
    send_token(docID)


@app.post("/recvToken/")
def recv_token(docID: int, background_task: BackgroundTasks):
    logger.info(f"Received token: {docID}")
    time.sleep(0.1)
    if doc_queues[docID]:
        head = doc_queues[docID].pop(0)
        doc_permission[head] = True
        return {f"Using the token for the following docID: {docID}"}
    else:
        background_task.add_task(send_token, docID) # NOTE: Has to run as a background task or the calling send_token function in the ansestor waits forever
        return {f"Do not need following id {docID}, passed it to my successor {server_list[successor]}"}


def send_token(docID: int):
    logger.info(f"Sending token to {server_list[successor]} for docID {docID}")
    reply = requests.post(f"http://{server_list[successor]}/recvToken/", params={"docID": docID})
    logger.info(str(reply.content))

@app.post("/heartBeatCheck/")
def heart_beat_check():
    return {"Message": "Got hearbeat"}


@app.websocket("/ws/{document_id}/{docName}")
async def websocket_endpoint(websocket: WebSocket, document_id: int, docName: str, s: Session):
    logger.info("running")
    await manager.connect(document_id, websocket)

    logger.info(f"{document_id} {docName}")
    doc = await read_document(s, document_id)

    await websocket.send_text(doc.content)

    try:
        while True:
            # Data is client request to edit
            data = await websocket.receive_text()
            logger.info(data)

            doc_queues[document_id].append(websocket)
            doc_permission[websocket] = False
            logger.info(f"Adding websocket to queue for docID: {document_id}")
            # Loop the socket while you don't have permission
            while not doc_permission[websocket]:
                logger.info(f"{doc_permission[websocket]}")
                logger.info("Waiting for permission")
                await asyncio.sleep(0.1)
                continue

            logger.info("telling client, lock acquired")

            await websocket.send_text("*** START EDITING ***")

            while True:
                data = await websocket.receive_text()
                # parse data json
                json_data = json.loads(data)
                data = json_data['content']
                if (data == "*** STOP EDITING ***"):
                    logger.info("Client said done editing")
                    send_token(document_id)
                    break

                logger.info("Content: ")
                logger.info(data)

                # Update document in this replica's database
                doc = await update_document(s, DocumentUpdate(content=data, id=document_id, name=docName))
                # NOTE: Broadcast changes to any websockets on THIS replica working on that document
                await manager.broadcast(document_id, data)

                for server_info in server_list:
                    server = server_info.split(':')
                    # Don't update yourself
                    if server[0] == MY_IP and server[1] == MY_PORT:
                        continue
                    try:
                        response = await connect_to_replica(document_id, docName, doc.content, server[0], server[1])
                    except TimeoutError:
                        server_list.remove(server_info)
                        logger.info("Server_list after removing server which caused the time out: ")
                        logger.info(server_list)
                        continue
    except WebSocketDisconnect:
        manager.disconnect(document_id, websocket)
        # Inform server you lost a connection from a client (NOTE: Master is hard coded to be on localhost port 8000)
        response = requests.post(f"http://{MASTER_IP}:8000/lostClient/", params={"docID": document_id})
        if doc_permission[websocket] == True:
            send_token(document_id) # TODO: What to do if the client closes tab without pressing stop edit button
        logger.info(response)
        # Then disconnect


# create websocket to connect to replica
async def connect_to_replica(document_id: int, docName: str, content: str, IP: str, port: str):
    uri = f"ws://{IP}:{port}/replica/ws/{document_id}/{docName}"
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
        raise TimeoutError # NOTE: TEMP CHANGE, DEAL WITH EXCEPTIONS PROPERLY
    except Exception as e:
        print(f"An error occurred: {e}")
        raise


@app.websocket("/replica/ws/{document_id}/{docName}")
async def replica_websocket_endpoint(websocket: WebSocket, document_id: int, docName: str, s: Session):
    await manager.connect(document_id, websocket)
    print(f"Connected to document {document_id} with name {docName}")

    doc = await read_document(s, document_id)

    try:
        while True:
            data = await websocket.receive_text()
            print(docName)
            print(data)
            # parse data json
            data = json.loads(data)['content']

            # Update the document in your replicate database
            doc = await update_document(s, DocumentUpdate(content=data, id=document_id, name=docName))
            # NOTE: Broadcast changes to any clients who might be waiting to edit the document
            await manager.broadcast(document_id, data)

            await websocket.send_text(f"ack from replica {MY_PORT}")
    except WebSocketDisconnect:
        manager.disconnect(document_id, websocket)
        print(f"Connection closed with exception")

# For testing
@app.post("/createDoc/", response_model=Document)
async def create_doc(docID: int, docName: str, docContent: str, s: Session):
    doc = await create_document_with_content(s, docName, docContent)
    return doc


"""
@app.get("/users/")
async def get_users(s: Session) -> list[User]:
    return await read_users(s)


@app.post("/users/")
async def post_user(s: Session, uc: UserCreate) -> User:
    return await create_user(s, uc)
"""