from contextlib import asynccontextmanager
from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional, Annotated, List, Any
import requests
#import aiohttp  NOTE: The 'requests' module is not asyncronous, this one is ... I am not sure if being sychornous will issues
import logging
from threading import Lock, Timer
import json


# From: https://stackoverflow.com/questions/56167390/resettable-timer-object-implementation-python
class ResettableTimer(object):
    def __init__(self, interval, function, docID):
        self.interval = interval
        self.function = function
        self.docID = docID
        self.timer = Timer(self.interval, self.function, [self.docID])
        logger.info(f"Token generated for docID: {self.docID}")

    def run(self):
        self.timer.start()

    def reset(self):
        self.timer.cancel()
        self.timer = Timer(self.interval, self.function, [self.docID])
        self.timer.start()
        logger.info(f"Resetting the timer for docID: {self.docID}")

    def inUse(self):
        #TODO: Check if a reset() call after this cancel causes problems due to canceling a
        # canceled timer
        self.timer.cancel()

class ServerInfo:
    def __init__(self, IP_PORT: str, clients_online: int) -> None:
        self.IP_PORT = IP_PORT
        self.clients_online = clients_online

class OpenDocInfo:
    def __init__(self, IP_PORT: str, conn: int) -> None:
        self.IP_PORT = IP_PORT
        self.connections = conn

# GLOBAL VARIABLES for instance of master server
# NOTE: The timeout before another token is regenerated is controlled by the integer provided as the first paramater
# to object instansiation e.g. 'ResettableTimer(20, token_timeout, docID)' time out after 20 seconds
tokens_not_initialized = True
docID_timers: dict[int, ResettableTimer] = {}

# Startup event for heartbeat
#@asynccontextmanager
#async def lifespan(app: FastAPI):
#    b_t = BackgroundTasks()
#    b_t.add_task(loop_servers_heartbeat) # TODO: Might be blocking/cause issues
#    yield

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

            except Exception as e:
                print(f"Failed to broadcast server list to server at IP {server}: {e}")
        
        # tell one server to start circulating the tokens for the documents
        global tokens_not_initialized
        if (tokens_not_initialized and len(server_list) >= 2):

            # Get the list of document_ids which need to be tracked by the heartbeat
            server = server_list[0].split(':')
            ret_obj = requests.get(f'http://{server[0]}:{server[1]}/docList/')
            logger.info("docList return object")
            doc_list = ret_obj.json()
            logger.info(doc_list)

            # NOTE: only work on the document list if it is not empty
            if doc_list:
                global docID_timers
                docID_list = [int(doc['id']) for doc in doc_list]
                logger.info("List of Doc IDs in master:")
                logger.info(docID_list)
                # Start the 5 second timers for the tokens
                for docID in docID_list:
                    docID_timers[docID] = ResettableTimer(20, token_timeout, docID)
                    docID_timers[docID].run()

            # Start the token circulation
            logger.info("Reached before tokens call")
            ack = requests.post(f"http://{server[0]}:{server[1]}/initializeTokens/")
            tokens_not_initialized = False
            logger.info("Reached after tokens call")
        
        logger.info("Done broadcasting to servers")

@app.post("/lostClient/{ip}/{port}/")
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

    # Create a token for the new document and add it to the list of DocIDs which need to be checked by the heartbeat
    response = requests.post(f"http://{server[0]}:{server[1]}/initializeToken/{docID}/")
    logger.info(response)

    # Start the 5 second timer for this new token
    global docID_timers
    docID_timers[docID] = ResettableTimer(20, token_timeout, docID)
    docID_timers[docID].run()

    return {"docID": docID, "docName": docName, "IP": server[0], "port": server[1]}


# TODO: docID not currently used in this request (might be needed for tolerance)
@app.post("/connectToExistingDoc/")
async def conn_to_existing_doc(docID: str = Body()):
    docID = int(docID)

    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more client to this replica
    server = server_docs[index].IP_PORT
    server = str(server).split(':')

    return {"IP": server[0], "port": server[1]}


@app.get("/docList/")
def doc_list() -> Any:
    # defaulting to getting list from the first server
    ret_obj = requests.get(f'http://{server_docs[0].IP_PORT.split(':')[0]}:{server_docs[0].IP_PORT.split(':')[1]}/docList/')
    logger.info("docList return object, requested by client")
    logger.info(ret_obj.json())
    return ret_obj.json()



### Functions for fault tolerance ###
# Restart token if a timeout is reached
def token_timeout(docID: int):
    logger.info(f"DocID's {docID} token timedout, asking leader to generate a new token")
    server = server_docs[0].IP_PORT
    server = str(server).split(':')
    response = requests.post(f"http://{server[0]}:{server[1]}/initializeToken/{docID}/")

@app.post("/tokenInUse/{docID}/")
def token_in_use(docID: int):
    global docID_timers
    docID_timers[docID].inUse()
    return {"Message": f"ack for {docID}"}


@app.post("/replicaRecvToken/{docID}/")
async def replica_received_token(docID: int):
    global docID_timers
    # NOTE: docID should always be in the dict (if it isn't then something when very wrong)
    docID_timers[docID].reset()
    return {"Message": f"ack for {docID}"}


@app.post("/succCrashed/{crashed_ip}/{crashed_port}/")
def replica_successor_crashed(crashed_ip: str, crashed_port: str, background_task: BackgroundTasks):
    crashed_ip_port = crashed_ip + ":" + crashed_port
    # find the server with that IP and port
    global server_docs
    servers = [x.IP_PORT for x in server_docs]
    if crashed_ip_port in servers:
        index = servers.index(crashed_ip_port)
        server_docs.pop(index)
        # NOTE: update other replicas if this is the first crash detected of that replica
        # This was causing problems...
        # background_task.add_task(broadcast_servers(server_docs))
        logger.info("Popped dead server from list in master")
    
    return {"Message": "ack crash of succesor"}


@app.post("/lostConnection/")
async def transfer_conn(background_task: BackgroundTasks, data_str: str = Body()):
    data = json.loads(data_str)

    # Client provide the document they were working with and the IP and PORT they got no response from
    ip = data['IP']
    port = data['PORT']
    docID = int(data['docID'])

    global server_docs # NOTE: Need global to stop 'UnboundLocalError' as we are reassgining to server_docs within the function

    client_IP_PORT = ip + ':' + port

    servers = [x.IP_PORT for x in server_docs]
    logger.info("server_list before any if/else logic and removal of dead server")
    logger.info(servers)

    if client_IP_PORT in servers:
        index = servers.index(client_IP_PORT)
        server_docs.pop(index) # remove the server from the active list of servers
        # Update the serverlist in the replicas if this is the first time a crash of this replica is detected
        #background_task.add_task(broadcast_servers(server_docs))

    if not server_docs:
        return {"Error": "no servers online to connect too"}
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more doc being managed by this replica

    server = server_docs[index].IP_PORT
    server = str(server).split(':')
    logger.info("Client rerouted to:")
    logger.info(server)

    return {"IP": server[0], "port": server[1]}




"""
# heartbeat to check if all servers in server is still alive
def loop_servers_heartbeat():
    while True:
        heartbeat(server_docs)   
        time.sleep(5) 


def heartbeat(server_docs: list[ServerInfo]):
    server_list = [x.IP_PORT for x in server_docs] # get the IP_PORT info from the objects
    if docID_list: # NOTE: only do the check if there are tokens to verify
        for server in server_list:
            try:
                server = str(server).split(':')
                response = requests.post(f"http://{server[0]}:{server[1]}/heartbeatCheck/", data={"heartbeat": "True"})
                logger.info(response)

                if response.status_code == 404:
                    logger.info(f"Server at IP {server}")

            except Exception as e:
                print(f"Failed to broadcast heartbeat to server at IP {server}: {e}")
"""