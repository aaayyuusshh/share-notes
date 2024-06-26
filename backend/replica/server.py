from contextlib import asynccontextmanager
from typing import Annotated, List, Any, Tuple, Dict
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
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
    doc_list_db
)
import websockets
import requests
import time
import asyncio
from threading import Lock

# alternative to directly defining paramter type
from pydantic import BaseModel

class Server(BaseModel):
    IP: str
    port: str

Session = Annotated[AsyncSession, Depends(session)]

logger = logging.getLogger("uvicorn")

# Global arrays and queues
server_list = []
successor = 0
doc_queues: dict[int, list] = {}
doc_permission: dict[WebSocket, bool] = {}
send_token_count = 0
serial_of_token: dict[int, int] = {}
# NOTE: Lock is needed as multiple attempts can be made to pass tokens to a dead successor within a short time window
# the lock avoids faulty deletes in that scenerio
succ_lock = Lock()

# Enviroment variables
MY_PORT = os.getenv("PORT")
logger.info(MY_PORT)

MY_IP = os.getenv("IP")
logger.info(MY_IP)

MASTER_IP = os.getenv("MASTER_IP")
logger.info(MASTER_IP)


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
        logger.info(f"Creating empty document lists for document: {doc[0]}")
        doc_queues[int(doc[0])] = []

# Http post request to create a new document
@app.post("/newDocID/{docName}/")
async def create_docID(s: Session, docName: str):
    docID = await create_document(s, docName)
    doc_queues[docID] = [] # create queue for docID
    return {"docID": docID}

# Http post request to get docList
@app.get("/docList/", response_model=List[DocumentList])
async def doc_list(s: Session) -> Any:
    docList = await s.execute(select(Document.id, Document.name))
    return docList


# Updating server list to reflect any changes in the master
@app.post("/updateServerList/")
async def update_server_list(new_server_list: list[str]):
    global server_list
    global successor
    server_list = new_server_list
    index = server_list.index(f"{MY_IP}:{MY_PORT}")
    successor = (index+1) % len(server_list)
    logger.info("Updated server list: ")
    logger.info(server_list)
    logger.info("Index of successor: ")
    logger.info(successor)

    return {"message": "Server list updated successfully"}


# For every document in its documement list, create a token and send it to its successor
@app.post("/initializeTokens/")
async def initialize_tokens(s: Session, background_task: BackgroundTasks):
    logger.info("INITIALIZE TOKENS (ALL)")
    docList = await s.execute(select(Document.id, Document.name))
    logger.info(f"List of documents from db for which tokens will be generated: {docList}")
    for doc in docList:
        # NOTE: all tokens initially start with serial number 1
        background_task.add_task(send_token, int(doc[0]), 1)
    return {"Message": "Tokens initialized"}


# Create a token ONLY for the specified docID:serial-number
@app.post("/initializeToken/{token_id}/{token_serial}/")
async def initialize_token(token_id: int, token_serial: int, background_task: BackgroundTasks):
    logger.info("INITIALIZE TOKEN (ONE)")
    background_task.add_task(send_token, token_id, token_serial)
    return {"Message": "Token initialized"}

# Handle recieving token
@app.post("/recvToken/{token_id}/{token_serial}/")
def recv_token(token_id: int, token_serial: int, background_task: BackgroundTasks):
    logger.info(f"Received token: {token_id}:{token_serial}")

    if doc_queues[token_id]:
        # NOTE: Have to remember the serial number for the tokens you are using (needed for when you release the edit lock)
        global serial_of_token
        serial_of_token[token_id] = token_serial
        # Get the websocket at the head of the queue
        head = doc_queues[token_id].pop(0)
        doc_permission[head] = True
        return {"Using": "true"}
    else:
        background_task.add_task(send_token, token_id, token_serial) # NOTE: Has to run as a background task or the calling send_token function in the ancestor waits forever
        return {"Using": "false"}

# Handle sending token
def send_token(token_id: int, token_serial: int):
    # Inform master that you received the token before sending it
    reply_master = requests.post(f"http://{MASTER_IP}:8000/replicaRecvToken/{token_id}/{token_serial}/")
    reply_master_resp = reply_master.json()
    logger.info(f"reply from master: {reply_master_resp}")
    # If true then this token should not be in circulation ... let it disappear silently
    if (reply_master_resp['Token'] == "invalid"):
        logger.info("Invalid token detected, was not propogated...")
        return

    # Loop for passing token to successor ... successfully
    while True:
        try:
            global successor
            global server_list

            time.sleep(2)
            logger.info(f"Server_list before call to recvToken: {server_list}")
            with succ_lock:
                succ_server = server_list[successor]
            logger.info("Sending token")
            reply_succ = requests.post(f"http://{succ_server}/recvToken/{token_id}/{token_serial}/")
            reply_succ_resp = reply_succ.json()
            logger.info(f"reply for recvToken to successor: {reply_succ_resp}")
            if (reply_succ_resp['Using'] == "true"):
                reply_token_use = requests.post(f"http://{MASTER_IP}:8000/tokenInUse/{token_id}/{token_serial}/")
            
            logger.info(f"Sent token ({token_id}:{token_serial}) to {succ_server}")
            break # done if post request returned successfully
        
        except Exception as e:

            logger.info(f"handling send_token exceptions: {e}")
            logger.info(f"Current successor index: {successor}")

            # inform master of replica crash
            bad_ip_port = succ_server.split(':')
            reply = requests.post(f"http://{MASTER_IP}:8000/replicaCrashed/{bad_ip_port[0]}/{bad_ip_port[1]}/")

            # pop the bad successor out of the local ring if it exists in the server list
            # within a lock to avoid duplicate modfications
            with succ_lock:
                if succ_server in server_list:
                    succ_index = server_list.index(succ_server)
                    server_list.pop(succ_index)
                    # set new successor
                    index = server_list.index(f"{MY_IP}:{MY_PORT}")
                    successor = (index+1) % len(server_list)

            logger.info(f"Successor updated to index: {successor}")

            continue # try again (done in loop to avoid recursion)


@app.websocket("/ws/{document_id}/{docName}/{editPerm}/")
async def websocket_endpoint(websocket: WebSocket, document_id: int, docName: str, editPerm: str, s: Session):
    global server_list
    global successor

    logger.info("editPerm:")
    logger.info(editPerm)
    await manager.connect(document_id, websocket)

    logger.info(f"{document_id} {docName}")
    doc = await read_document(s, document_id)

    if editPerm == "true":
        await websocket.send_text("*** START EDITING ***")
    
    await websocket.send_text(doc.content)

    try:
        while True:
            if editPerm == "true":
                doc_permission[websocket] = True # Client was editing before disconnect, so let them continue editing
                editPerm = "false" # following requests to edit will have to jump through regular permission logic

            else:
                # Data is client request to edit
                data = await websocket.receive_text()
                logger.info(data)
                # add the client to the queue of websockets waiting for that document
                doc_queues[document_id].append(websocket)
                logger.info(f"Adding websocket to queue for docID: {document_id}")
                doc_permission[websocket] = False
            
                # Loop the socket while you don't have permission
                while not doc_permission[websocket]:
                    logger.info(f"{doc_permission[websocket]}")
                    logger.info("Waiting for permission")
                    await asyncio.sleep(2)
                    continue

                await websocket.send_text("*** START EDITING ***")

            logger.info("telling client, lock acquired")

            while True:
                data = await websocket.receive_text()
                # parse data json
                json_data = json.loads(data)
                data = json_data['content']
                if (data == "*** STOP EDITING ***"):
                    logger.info("Client said done editing")
                    doc_permission[websocket] = False
                    send_token(document_id, serial_of_token[document_id])
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
                        if server_info in server_list:
                            server_list.remove(server_info)
                            logger.info("Server_list after removing server which caused the time out: ")
                            logger.info(server_list)
                            # set new successor
                            index = server_list.index(f"{MY_IP}:{MY_PORT}")
                            successor = (index+1) % len(server_list)
                            continue
    except WebSocketDisconnect:
        manager.disconnect(document_id, websocket)
        # Inform server you lost a connection from a client (NOTE: Master is hard coded to be on localhost port 8000)
        response = requests.post(f"http://{MASTER_IP}:8000/lostClient/{MY_IP}/{MY_PORT}/")
        # If client closes tab without pressing stop editing, then pass the token along
        if websocket in doc_permission:
            if doc_permission[websocket] == True:
                send_token(document_id, serial_of_token[document_id])
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

# websocket connections for replication
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

# For demoing
@app.post("/createDoc/", response_model=Document)
async def create_doc(docID: int, docName: str, docContent: str, s: Session):
    doc = await create_document_with_content(s, docName, docContent)
    return doc