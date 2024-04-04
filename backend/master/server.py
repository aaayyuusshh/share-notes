from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional, Annotated, List, Any
import requests
#import aiohttp  NOTE: The 'requests' module is not asyncronous, this one is ... I am not sure if being sychornous will issues
import logging
from threading import Lock
import json
import time

class ServerInfo:
    def __init__(self, IP_PORT: str, clients_online: int) -> None:
        self.IP_PORT = IP_PORT
        self.clients_online = clients_online

class OpenDocInfo:
    def __init__(self, IP_PORT: str, conn: int) -> None:
        self.IP_PORT = IP_PORT
        self.connections = conn

# GLOBAL VARIABLES for instance of master server
tokens_not_initialized = True

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop_servers_hearbeat()
    yield

# Create an instance of the FastAPI class
app = FastAPI(title="Master Server", lifespan=lifespan)

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

### End points to deal with server requests and updates ###

@app.post("/addServer/")
async def con_server(IP: str, port: str, background_task: BackgroundTasks):
    with lock:
        # Track number of clients on the server
        servers = [x.IP_PORT for x in server_docs]
        if f"{IP}:{port}" not in servers:
            server_docs.append(ServerInfo(f"{IP}:{port}", 0))
        # inform other servers that a new one joined
        background_task.add_task(broadcast_servers, server_docs)
    return {"Message": "Server added to cluster"}

def broadcast_servers(server_docs: list[ServerInfo]):
    server_list = [x.IP_PORT for x in server_docs] # get the IP_PORT info from the objects
    with lock:
        for server in server_list:
            try:
                server = str(server).split(':')
                response = requests.post(f"http://{server[0]}:{server[1]}/updateServerList/", data=json.dumps(server_list))
                logger.info(response)

            except Exception as e:
                print(f"Failed to broadcast server list to server at IP {server}: {e}")
        
        # tell one server to start circulating the tokens for the documents
        global tokens_not_initialized
        server = server_list[0].split(':')
        if (tokens_not_initialized and len(server_list) >= 2):
            ack = requests.post(f"http://{server[0]}:{server[1]}/initializeTokens/")
            logger.info(ack)
            tokens_not_initialized = False

@app.post("/lostClient/{ip}/{port}")
async def lost_client(ip: str, port: str):
    server_list = [x.IP_PORT for x in server_docs]
    index = server_list.index(f"{ip}:{port}")
    server_list[index] -= 1 # Decreament client number

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
    
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more client to this replica
    server = server_docs[index].IP_PORT
    server = str(server).split(':')

    response = requests.post(f"http://{server[0]}:{server[1]}/initializeToken/{docID}/")
    logger.info(response)

    return {"docID": docID, "docName": docName, "IP": server[0], "port": server[1]}


# TODO: docID not currently used in this requestion (might be needed for tolerance)
@app.post("/connectToExistingDoc/")
async def conn_to_existing_doc(docID: str = Body()):
    docID = int(docID)

    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more client to this replica
    server = server_docs[index].IP_PORT
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
    #TODO: Again, rerouting doesn't consider the possibility the client was wrong and thus doesn't track the docID
    docID = int(data['docID']) 

    global server_docs # NOTE: Need global to stop 'UnboundLocalError' as we are reassgining to server_docs within the function
    
    # For logging purposes 
    server_list = [x.IP_PORT for x in server_docs]
    logger.info("server_list before any if/else logic and removal of dead server")
    logger.info(server_list)

    client_IP_PORT = ip + ':' + port
    server_docs = [s_doc for s_doc in server_docs if s_doc.IP_PORT != client_IP_PORT] # remove the server from the active list of servers
    if not server_docs:
        return {"Error": "no servers online to connect too"}
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more doc being managed by this replica

    server = server_docs[index].IP_PORT
    server = str(server).split(':')
    logger.info("Client rerouted to:")
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

# heartbeat to check if all servers in server is still alive
def loop_servers_hearbeat():
    while True:
        heartbeat(server_docs)   
        time.sleep(5) 

def heartbeat(server_docs: list[ServerInfo]):
    server_list = [x.IP_PORT for x in server_docs] # get the IP_PORT info from the objects
    with lock:
        for server in server_list:
            try:
                server = str(server).split(':')
                response = requests.post(f"http://{server[0]}:{server[1]}/heartbeatCheck/", data={"heartbeat": "True"})
                logger.info(response)

                if response.status_code == 404:
                    logger.info(f"Server at IP {server}")

            except Exception as e:
                print(f"Failed to broadcast heartbeat to server at IP {server}: {e}")
    
