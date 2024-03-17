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

class ServerInfo:
    def __init__(self, IP_PORT: str, docsOpen: int) -> None:
        self.IP_PORT = IP_PORT
        self.docsOpen = docsOpen

class OpenDocInfo:
    def __init__(self, IP_PORT: str, conn: int, t_status: bool, con_t: int) -> None:
        self.IP_PORT = IP_PORT
        self.connections = conn
        self.not_transfering = t_status
        self.conn_transfered = con_t

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
server_docs: list[ServerInfo] = []
lock = Lock() # NOTE: Lock is from threading, might have to use multiprocesser lock if uvicorn launches multiple processes (I don't think it does)

# Tracking doc-primary_replica-clients coupling
open_docs: dict[int, OpenDocInfo] = {}

# TODO: a return to home screen and save button which will inform the server when a clinet disconnected 
# NOTE: This can be done in the disconnect exception handling in the actual replica


### End points to deal with server requests and updates ###

@app.post("/addServer/")
async def con_server(IP: str, port: str, background_task: BackgroundTasks):
    with lock:
        # Track number of open docs on the server
        server_docs.append(ServerInfo(f"{IP}:{port}", 0))
        logger.info(server_docs)
        # inform other servers that a new one joined
        background_task.add_task(broadcast_servers, server_docs)
    return {"message": "Server added to cluster"}

def broadcast_servers(server_docs: list[ServerInfo]):
    server_list = [x.IP_PORT for x in server_docs] # get the IP_PORT info from the objects
    with lock:
        for server in server_list:
            try:
                server = str(server).split(':')
                requests.post(f"http://{server[0]}:{server[1]}/updateServerList/", data=json.dumps(server_list))
            except Exception as e:
                print(f"Failed to broadcast server list to server at IP {server}: {e}")

@app.get("/lostClient/")
async def lost_client(docID: int):
    open_docs[docID].connections -= 1 # decreament client number
    if open_docs[docID][1] == 0: 
        # if no more client ... remove this docID from being active
        try: 
            index = [ x.IP_PORT for x in server_docs ].index(open_docs[docID].IP_PORT)
            server_docs[index] -= 1 # this replica is tracking one less document (increasing it priority to take on more docs in the future)
            return {"message": "Client lose acknowledged"}
        except ValueError:
            return {"Error": "Could not find the replica server the document was on"} # should never run


### End points to deal with client request ###
                
@app.post("/createDocAndConnect/")
async def create_doc_and_conn(docName: str = Body()):
    docID = -1
    with lock:
        for server in server_docs:
            try:
                server = server.IP_PORT.split(':')
                # This should ideally be passed as 'data=' parameter in the post request, but it causes issues with the naming
                ret_obj = requests.post(f"http://{server[0]}:{server[1]}/newDocID/{docName}/")
                logger.info(ret_obj.json())
                docID = ret_obj.json()["docID"]
                logger.info(docID)
            except Exception as e:
                print(f"Failed to broadcast server list to server at IP {server}: {e}")
    if (docID == -1):
        logger.info("Error occured with creating document")
    
    # Getting replica with least amount of documents open (NOTE: This can be done as a complex pq with update functionality, but seems pointless for list of 4 replicas)
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].docsOpen)
    server_docs[index].docsOpen += 1 # Add one more doc being managed by this replica
    open_docs[docID] = OpenDocInfo(server_docs[index].IP_PORT, 1, True, 0) # Track this document as in use and number of clients as 1

    server = open_docs[docID][0] # get the IP:PORT
    server = str(server).split(':')

    return {"docID": docID, "docName": docName, "IP": server[0], "port": server[1]}

@app.post("/connectToExistingDoc/")
async def conn_to_existing_doc(docID: str = Body()):
    docID = int(docID)

    if docID in open_docs:
        open_docs[docID].connections += 1 # Increment number of clients for that document by 1
    else:
        # Get replica server with the least amount of documents open
        index = min(range(len(server_docs)), key=lambda i: server_docs[i].docsOpen)
        server_docs[index].docsOpen += 1 # Add one more doc being managed by this replica
        open_docs[docID] = OpenDocInfo(server_docs[index].IP_PORT, 1, True, 0) # Track this document as in use and number of clients as 1

    server = open_docs[docID][0] # get the IP:PORT
    server = str(server).split(':')

    return {"IP": server[0], "port": server[1]}

@app.post("/lostConnection/")
async def transfer_conn(docID: str = Body()):
    docID = int(docID)

    logger.info("docID:")
    logger.info(docID)

    # if the information currently says true, this is the first client to come with a disconnect request
    if open_docs[docID].not_transfering:
        logger.info("Value added to set:")
        logger.info(open_docs[docID].IP_PORT)
        server_docs.remove(open_docs[docID].IP_PORT) # remove the server from the active list of servers

        if not server_docs:
            return {"Error": "no servers online to connect too"}
        # Get replica server with the least amount of documents open
        index = min(range(len(server_docs)), key=lambda i: server_docs[i].docsOpen)
        server_docs[index].docsOpen += 1 # Add one more doc being managed by this replica
        open_docs[docID].IP_PORT = server_docs[index].IP_PORT
        open_docs[docID].conn_transfered += 1 # 1 more connection transfered
  
    else:
        open_docs[docID].conn_transfered += 1

    # if true then everyone has been transfered over
    if open_docs[docID].connections == open_docs[docID].conn_transfered:
        open_docs[docID].not_transfering = True # set to true so disconnect on this IP:PORT can be responded to
        open_docs[docID].conn_transfered = 0 # reset tracker for connections transfered

    server = open_docs[docID].IP_PORT # get the IP:PORT
    server = str(server).split(':')
    logger.info("server:")
    logger.info(server)

    return {"IP": server[0], "port": server[1]}


# TODO: Make this async if needed, was causing issues previously
@app.get("/docList/")
def doc_list() -> Any:
    # defaulting to getting list from the first server
    ret_obj = requests.get(f'http://{server_docs[0].IP_PORT.split(':')[0]}:{server_docs[0].IP_PORT.split(':')[1]}/docList/')
    logger.info(ret_obj.json())
    return ret_obj.json()
