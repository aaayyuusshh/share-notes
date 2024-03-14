from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional, Annotated, List, Any
import requests
#import aiohttp  NOTE: The 'requests' module is not asyncronous, this one is ... I am not sure if being sychornous will issues
import logging
from sqlmodel import Field, SQLModel
from threading import Lock
import json
import heapq

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


# Create an instance of the FastAPI class
app = FastAPI(title="Master Server")

# Adding CORS permissions for client
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

logger = logging.getLogger("uvicorn")

# Tracking servers in the cluster
server_list = []
lock = Lock() # NOTE: Lock is from threading, might have to use multiprocesser lock if uvicorn launches multiple processes (I don't think it does)

# Tracking doc-primary_replica-clients coupling
d_pr_c = {}
pq = []
# dead_servers = set()

# TODO: a return to home screen and save button which will inform the server when a clinet disconnected 
# NOTE: This can be done in the disconnect exception handling in the actual replica

@app.post("/addServer/")
async def con_server(IP: str, port: str, background_task: BackgroundTasks):
    with lock:
        server_list.append(f"{IP}:{port}")
        # add to pq with 0 running documents being managed
        heapq.heappush(pq, (0, len(pq), f"{IP}:{port}"))
        logger.info(server_list)
        # inform other servers that a new one joined
        background_task.add_task(broadcast_servers, server_list)
        #broadcast_servers(server_list)
    return {"message": "Server added to cluster"}


def broadcast_servers(server_list: dict):
    with lock:
        for server in server_list:
            try:
                server = str(server).split(':')
                requests.post(f"http://{server[0]}:{server[1]}/updateServerList/", data=json.dumps(server_list))
            except Exception as e:
                print(f"Failed to broadcast server list to server at IP {server}: {e}")


@app.post("/createDocAndConnect/")
async def create_doc_and_conn(docName: str = Body()):
    docID = -1
    with lock:
        for server in server_list:
            try:
                server = str(server).split(':')
                # This should ideally be passed as 'data=' parameter in the post request, but it causes issues with the naming
                ret_obj = requests.post(f"http://{server[0]}:{server[1]}/newDocID/{docName}/")
                logger.info(ret_obj.json())
                docID = ret_obj.json()["docID"]
                logger.info(docID)
            except Exception as e:
                print(f"Failed to broadcast server list to server at IP {server}: {e}")
    if (docID == -1):
        logger.info("Error occured with creating document")
    
    # Getting replica with least amount of documents open
    head = heapq.heappop(pq)
    d_pr_c[docID] = [head[2], 1, True, 0] # third item in pq tuple is the IP:PORT and set number of readers to 1
    heapq.heappush(pq, (head[0]+1, head[1], head[2]))

    server = d_pr_c[docID][0] # get the IP:PORT
    server = str(server).split(':')

    return {"docID": docID, "docName": docName, "IP": server[0], "port": server[1]}


@app.post("/connectToExistingDoc/")
async def conn_to_existing_doc(docID: str = Body()):
    docID = int(docID)

    if docID in d_pr_c:
        d_pr_c[docID][1] += 1 # increment number of connections for that document by 1
    else:
        head = heapq.heappop(pq) # Get replica server with the least amount of documents open
        while head[2] not in server_list: # remove dead servers from pq (not ideal but you cant search a heap)
            head = heapq.heappop(pq)
        d_pr_c[docID] = [head[2], 1, True, 0] # third item in pq tuple is the IP:PORT and set number of readers to 1
        heapq.heappush(pq, (head[0]+1, head[1], head[2]))

    server = d_pr_c[docID][0] # get the IP:PORT
    server = str(server).split(':')

    return {"IP": server[0], "port": server[1]}


@app.post("/lostConnection/")
async def transfer_conn(docID: str = Body()):
    docID = int(docID)

    logger.info("docID:")
    logger.info(docID)

    # if the information currently says true, this is the first client to come with a disconnect request
    if d_pr_c[docID][2]:
        logger.info("Value added to set:")
        logger.info(d_pr_c[docID][0])
        server_list.remove(d_pr_c[docID][0]) # remove the server from the active lit of servers
        #dead_servers.add(d_pr_c[docID][0]) # add the server to the list of dead server

        head = heapq.heappop(pq) # Get replica server with the least amount of documents open
        logger.info("Head before loop:")
        logger.info(head)
        while head[2] not in server_list: # remove dead servers from pq (not ideal but you cant search a heap)
            head = heapq.heappop(pq)
            if not pq:
                return {"Error": "no servers online to connect too"}
        logger.info("Head after loop:")
        logger.info(head)
        d_pr_c[docID][0] = head[2]
        d_pr_c[docID][3] += 1
        heapq.heappush(pq, (head[0]+1, head[1], head[2]))

        # if true everyone has been transfered over
        if d_pr_c[docID][1] == d_pr_c[docID][3]:
            d_pr_c[docID][2] = True # set to true so disconnect on this IP:PORT can be responded to
            d_pr_c[docID][3] = 0 # reset tracker for connections transfered
  
    else:
        d_pr_c[docID][3] += 1
        # if true everyone has been transfered over
        if d_pr_c[docID][1] == d_pr_c[docID][3]:
            d_pr_c[docID][2] = True
            d_pr_c[docID][3] = 0 # reset tracker for connections transfered

    server = d_pr_c[docID][0] # get the IP:PORT
    server = str(server).split(':')
    logger.info("server:")
    logger.info(server)

    return {"IP": server[0], "port": server[1]}


@app.get("/docList/")
def doc_list() -> Any:
    # defaulting to getting list from the first server
    ret_obj = requests.get(f'http://{str(server_list[0]).split(':')[0]}:{str(server_list[0]).split(':')[1]}/docList/')
    logger.info(ret_obj.json())
    return ret_obj.json()
