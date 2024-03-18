from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional, Annotated, List, Any
import requests
#import aiohttp  NOTE: The 'requests' module is not asyncronous, this one is ... I am not sure if being sychornous will issues
import logging
from threading import Lock
import json
from pydantic import BaseModel

class ServerInfo:
    def __init__(self, IP_PORT: str, docsOpen: int) -> None:
        self.IP_PORT = IP_PORT
        self.docsOpen = docsOpen

class OpenDocInfo:
    def __init__(self, IP_PORT: str, conn: int) -> None:
        self.IP_PORT = IP_PORT
        self.connections = conn

class LostConnection(BaseModel):
    IP: str
    PORT: str
    docID: int

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
        logger.info([x.IP_PORT for x in server_docs])
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

@app.post("/lostClient/")
async def lost_client(docID: int):
    open_docs[docID].connections -= 1 # decreament client number
    # if no more client ... remove this docID from being active
    if open_docs[docID].connections == 0: 
        try: 
            index = [ x.IP_PORT for x in server_docs ].index(open_docs[docID].IP_PORT)
            server_docs[index].docsOpen -= 1 # this replica is tracking one less document (increasing it priority to take on more docs in the future)
            # open_docs.pop(docID, None) # ISSUE: Removes the key on server shutdown
            return {"Message": "Client lose acknowledged"}
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
    
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].docsOpen)
    server_docs[index].docsOpen += 1 # Add one more doc being managed by this replica
    open_docs[docID] = OpenDocInfo(server_docs[index].IP_PORT, 1) # Track this document as in use and number of clients as 1

    server = open_docs[docID].IP_PORT # get the IP:PORT
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
        open_docs[docID] = OpenDocInfo(server_docs[index].IP_PORT, 1) # Track this document as in use and number of clients as 1

    server = open_docs[docID].IP_PORT # get the IP:PORT
    server = str(server).split(':')

    return {"IP": server[0], "port": server[1]}

@app.post("/lostConnection/")
async def transfer_conn(data_str: str = Body()):
    data = json.loads(data_str)

    # Client provide the document they were working with and the IP and PORT they got no response from
    # TODO: This way of doing things puts full trust in the client, ideally the master would verify if the
    # server is actually dead by asking for a heartbeat 
    ip = data['IP']
    port = data['PORT']
    docID = int(data['docID'])

    logger.info("IP:")
    logger.info(ip)
    logger.info("PORT:")
    logger.info(port)
    logger.info("docID:")
    logger.info(docID)

    server_list = [x.IP_PORT for x in server_docs]
    logger.info(server_list)

    client_IP_PORT = ip + ':' + port

    # The first request to transfer will have the same IP_PORT
    if (docID not in open_docs) or (open_docs[docID].IP_PORT == client_IP_PORT):
        for server_doc in server_docs:
            if server_doc.IP_PORT == client_IP_PORT:
                server_docs.remove(server_doc) # remove the server from the active list of servers
        if not server_docs:
            return {"Error": "no servers online to connect too"}
        # Get replica server with the least amount of documents open
        index = min(range(len(server_docs)), key=lambda i: server_docs[i].docsOpen)
        server_docs[index].docsOpen += 1 # Add one more doc being managed by this replica
        open_docs[docID] = OpenDocInfo(server_docs[index].IP_PORT, 1) # new IP:PORT where the client will go to with 1 reader
    
    else:
        open_docs[docID].connections += 1 # 1 more connection on the new port

    server = open_docs[docID].IP_PORT # get the IP:PORT
    server = str(server).split(':')
    logger.info("server:")
    logger.info(server)

    return {"IP": server[0], "port": server[1]}


# TODO: Make this async if needed, was causing issues previously
@app.get("/docList/")
def doc_list() -> Any:
    logger.info(server_docs)
    # defaulting to getting list from the first server
    ret_obj = requests.get(f'http://{server_docs[0].IP_PORT.split(':')[0]}:{server_docs[0].IP_PORT.split(':')[1]}/docList/')
    logger.info(ret_obj.json())
    return ret_obj.json()
