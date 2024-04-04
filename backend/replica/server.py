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
from threading import Lock

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
send_token_count = 0
succ_lock = Lock() # NOTE: Lock is from threading, might have to use multiprocesser lock if uvicorn launches multiple processes (I don't think it does)


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
    logger.info(docList)
    for doc in docList:
        print("doc", doc[0])
        background_task.add_task(send_token, doc[0])
    return {"Message": "Tokens initialized"}


# Create a token ONLY for the specified docID
@app.post("/initializeToken/{docID}/")
async def initialize_token(docID: int, background_task: BackgroundTasks):
    logger.info("INITIALIZE TOKEN (ONE)")
    background_task.add_task(send_token, docID)
    return {"Message": "Token initialized"}


@app.post("/recvToken/")
def recv_token(docID: int, background_task: BackgroundTasks):
    logger.info(f"Received token: {docID}")
    
    if doc_queues[docID]:
        head = doc_queues[docID].pop(0)
        doc_permission[head] = True
        return {"Using": "true"}
    else:
        background_task.add_task(send_token, docID) # NOTE: Has to run as a background task or the calling send_token function in the ansestor waits forever
        return {"Using": "false"}


def send_token(docID: int):
    global send_token_count
    # Inform master that you received the token before sending it
    # NOTE: CHECK THIS DOES NOT CAUSE issues, previously had problems where this will lead to deadlock as master was waiting for response
    # to initalizeTokens but then also had to process ack of receiving the token
    reply_master = requests.post(f"http://{MASTER_IP}:8000/replicaRecvToken/{docID}/")
    logger.info(f"reply from master (token counter {send_token_count}): {reply_master}")

    while True:
        try:
            global successor
            global server_list

            logger.info("Sending token")
            time.sleep(0.1)
            logger.info(f"Server_list before call to recvToken (token counter {send_token_count}): {server_list}")
            with succ_lock:
                succ_server = server_list[successor]
            reply_succ = requests.post(f"http://{succ_server}/recvToken/", params={"docID": docID})
            reply_succ_resp = reply_succ.json()
            logger.info(f"reply for recvToken to successor: {reply_succ_resp}")
            if (reply_succ_resp['Using'] == "true"):
                reply_token_use = requests.post(f"http://{MASTER_IP}:8000/tokenInUse/{docID}/")
            
            logger.info(f"Sent token to {succ_server} for docID {docID}")
            break # done if post request returned succesfully
        # TODO: find the correct exceptions to catch
        except Exception as e:
            # NOTE (#1): The updates to the successor are local but the rebroadcast from the master about the new ring order might
            # be from a crash of another replica, leading to this replicas ring 'reverting' to an older version
            # this will cause another connection error but eventually the ring order given by master will settle
            # to one where all the crashed replicas have been removed

            # NOTE (#2): Ensure the timeout for lost tokens in master is 4 magnitudes greater at minimum then the sleep time between
            # receiving and passing tokens to avoid the issue of timeouts caused by replicas crashing leading to a delay in token
            # passing which is incorrectly interpreded by master as a lost token (all of this could be avoided if master had a seriel
            # id associated with tokens which it checked on the 'replicaRecvToken' post request to tell replica if it should pass the
            # token or drop it)
            
            logger.info(e)
            logger.info(f"handling send_token exceptions (token counter {send_token_count}): {server_list}")
            logger.info(f"Current successor (token counter {send_token_count}): {successor}")

            bad_ip_port = succ_server.split(':')
            reply = requests.post(f"http://{MASTER_IP}:8000/succCrashed/{bad_ip_port[0]}/{bad_ip_port[1]}/")
            logger.info(f"Reply from master for succ crash post (token counter {send_token_count}): {reply}")

            # pop the bad succesor out of the local ring if it exists in the server list
            #  within a lock to avoid duplicate modfications
            with succ_lock:
                if succ_server in server_list:
                    succ_index = server_list.index(succ_server)
                    server_list.pop(succ_index)
                    # set new successor
                    index = server_list.index(f"{MY_IP}:{MY_PORT}")
                    successor = (index+1) % len(server_list)

            logger.info(f"Successor updated to index (token counter {send_token_count}): {successor}")

            continue # try again (done in loop to avoid recursion)
    
    send_token_count += 1 # for logging purposes


# NOTE: 'editPerm' is an arugment to deal with replica crashing and allowing the client to continue editing
@app.websocket("/ws/{document_id}/{docName}/{editPerm}/")
async def websocket_endpoint(websocket: WebSocket, document_id: int, docName: str, editPerm: str, s: Session):
    logger.info("editPerm:")
    logger.info(editPerm)
    await manager.connect(document_id, websocket)

    logger.info(f"{document_id} {docName}")
    doc = await read_document(s, document_id)

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
                await asyncio.sleep(0.1)
                continue

            logger.info("telling client, lock acquired")

            # TODO: Ensure sending this again to clients on a reconnect from a replica crash does not cause issues
            await websocket.send_text("*** START EDITING ***")

            while True:
                data = await websocket.receive_text()
                # parse data json
                json_data = json.loads(data)
                data = json_data['content']
                if (data == "*** STOP EDITING ***"):
                    logger.info("Client said done editing")
                    doc_permission[websocket] = False # TODO: check if this is needed as the outer loop already does this
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
        response = requests.post(f"http://{MASTER_IP}:8000/lostClient/{MY_IP}/{MY_PORT}/")
        # If client closes tab without pressing stop editing, then
        if doc_permission[websocket] == True:
            send_token(document_id)
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
@app.post("/heartBeatCheck/")
def heart_beat_check():
    return {"Message": "Got hearbeat"}
"""


"""
@app.get("/users/")
async def get_users(s: Session) -> list[User]:
    return await read_users(s)


@app.post("/users/")
async def post_user(s: Session, uc: UserCreate) -> User:
    return await create_user(s, uc)
"""