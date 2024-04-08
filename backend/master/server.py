from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional, Annotated, List, Any
import requests
import logging
from threading import Lock, Timer
import json


# From: https://stackoverflow.com/questions/56167390/resettable-timer-object-implementation-python
# NOTE: The timeout before another token is regenerated is controlled by the integer provided as the first parameter
# to object instansiation e.g. 'ResettableTimer(20, token_timeout, docID)' time out after 20 seconds
class ResettableTimer(object):
    def __init__(self, interval, function, tokenID):
        self.interval = interval
        self.function = function
        self.tokenID = tokenID
        self.timer = Timer(self.interval, self.function, [self.tokenID])
        logger.info(f"Following token was generated: {self.tokenID}")

    def run(self):
        self.timer.start()

    def reset(self):
        self.timer.cancel()
        self.timer = Timer(self.interval, self.function, [self.tokenID])
        self.timer.start()
        logger.info(f"Resetting the timer for token: {self.tokenID}")

    def inUse(self):
        #TODO: Check if a reset() call after this cancel causes problems due to canceling a
        # canceled timer
        self.timer.cancel()
        logger.info(f"Marking token as in use (stopping its timer): {self.tokenID}")


class ServerInfo:
    def __init__(self, IP_PORT: str, clients_online: int) -> None:
        self.IP_PORT = IP_PORT
        self.clients_online = clients_online


# GLOBAL VARIABLES for instance of master server
leader_index = 0
# Tracking servers in the cluster
server_docs: list[ServerInfo] = []
server_list_lock = Lock() # NOTE: Precautionary lock to syncronize modification of of the server list
# Managing and tracking tokens
tokens_not_initialized = True
docID_timers: dict[str, ResettableTimer] = {}
token_list: list[str] = []



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


### End points to deal with server additions and updates ###
@app.post("/addServer/")
async def con_server(IP: str, port: str, background_task: BackgroundTasks):
    # Basic error checking
    if(not port.isdigit()):
        logger.info("Port provided was not a valid positive number")
        return {"Message": "Bad port provided"}
    
    with server_list_lock:
        servers = [x.IP_PORT for x in server_docs]
        if f"{IP}:{port}" not in servers:
            server_docs.append(ServerInfo(f"{IP}:{port}", 0))
            servers.append(f"{IP}:{port}") # add server to local copy for leader election
        # Pick a leader (lowest port number)
        # NOTE: add print statment to show the leader changing
        global leader_index
        ports = [int(server.split(':')[1]) for server in servers]
        leader_index = ports.index(min(ports))
        logger.info(f"Leader index is {leader_index} and its ip:port are {servers[leader_index]}")
        # inform other servers that a new one joined
        background_task.add_task(broadcast_servers, server_docs)
    return {"Message": "Server added to cluster"}

def broadcast_servers(server_docs: list[ServerInfo]):
    logger.info("Broadcasting updates to server_list")
    server_list = [x.IP_PORT for x in server_docs] # get the IP_PORT info from the objects
    # NOTE: behind a lock to ensure multiple tokens are not initalized and that updates provided to replicas for server lists are consistant
    with server_list_lock:
        for server in server_list:
            try:
                response = requests.post(f"http://{server}/updateServerList/", data=json.dumps(server_list))
            except Exception as e:
                logger.info(f"Failed to broadcast server list to {server} upon request from client, removing it from master list")
                ip_port = server.split(':')
                master_detect_replica_crashed(ip_port[0], ip_port[1])
        
        # tell the first server to start circulating the tokens for the documents
        global tokens_not_initialized
        if (tokens_not_initialized):

            # Get the list of document_ids which need to be tracked from the leader replica
            # NOTE: No check for if this server has crashed as this request is only made to the first server that just joined
            # if it already crashed ... then the system is not in a recoverable state and will need to be restarted
            ret_obj = requests.get(f'http://{server_list[leader_index]}/docList/')
            doc_list = ret_obj.json()

            # NOTE: only work on the document list if it is not empty
            if doc_list:
                global docID_timers
                global token_list
                docID_list = [int(doc['id']) for doc in doc_list]
                logger.info(f"List of Doc IDs in master: {docID_list}")
                # Start the timers for the tokens (serial number is 1 for the first token of that docID by default)
                for docID in docID_list:
                    token_list.append(f"{docID}:1")
                    docID_timers[f"{docID}:1"] = ResettableTimer(20, token_timeout, f"{docID}:1")
                    docID_timers[f"{docID}:1"].run()

            # Start the token circulation (done by the leader replica)
            # NOTE: No check for if this server has crashed as this request is only made to the first server that just joined
            # if it already crashed ... then the system is not in a recoverable state and will need to be restarted
            ack = requests.post(f"http://{server_list[leader_index]}/initializeTokens/")

            tokens_not_initialized = False
        
    logger.info("Done broadcasting updates to server_list")

# replica is informing master that it lost a client (useful for load balancing)
@app.post("/lostClient/{ip}/{port}/")
async def lost_client(ip: str, port: str):
    server_list = [x.IP_PORT for x in server_docs]
    index = server_list.index(f"{ip}:{port}")
    server_docs[index].clients_online -= 1 # Decreament client number



### End points to deal with client request ###     
@app.post("/createDocAndConnect/")
async def create_doc_and_conn(docName: str = Body()):
    global server_docs

    docID = -1
    with server_list_lock:
        for server in server_docs:
            try:
                ret_obj = requests.post(f"http://{server.IP_PORT}/newDocID/{docName}/")
                logger.info(ret_obj.json())
                docID = ret_obj.json()["docID"]
                logger.info(docID)
            except Exception as e:
                logger.info(f"Failed to create document at server {server.IP_PORT} upon request from client, removing it from master list")
                ip_port = server.IP_PORT.split(':')
                master_detect_replica_crashed(ip_port[0], ip_port[1])
    
    # NOTE: should theoretically never run as long as servers are connected in good faith
    if (docID == -1):
        logger.info("Error occured with creating document")
    
    # Get replica with the fewest clients
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more client to this replica
    server = server_docs[index].IP_PORT
    server = str(server).split(':')

    # Create a token for the new document
    new_token = f"{docID}:1"

    # Start the timer for this new token
    global docID_timers
    global token_list
    token_list.append(new_token)
    docID_timers[new_token] = ResettableTimer(20, token_timeout, new_token)
    docID_timers[new_token].run()

    # starts its circulation (done by leader replica)
    # NOTE: loop to check for when replica has crashed
    while True:
        try:
            global leader_index
            leader_server = server_docs[leader_index].IP_PORT
            # NOTE: first token for a given document has serial number of 1
            response = requests.post(f"http://{leader_server}/initializeToken/{docID}/1/")
            break
        except Exception as e:
            logger.info(f"Failed to initalize token for new document at leader {leader_server}, removing dead server from master list and trying again")
            ip_port = leader_server.split(':')
            master_detect_replica_crashed(ip_port[0], ip_port[1])
            continue


    return {"docID": docID, "docName": docName, "IP": server[0], "port": server[1]}

@app.post("/connectToExistingDoc/")
async def conn_to_existing_doc():
    # Get replica with the fewest clients
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more client to this replica
    server = server_docs[index].IP_PORT
    server = str(server).split(':')

    return {"IP": server[0], "port": server[1]}

@app.get("/docList/")
def doc_list() -> Any:
    # get document list from leaders (all replicas SHOULD have the same doclist)
    # NOTE: loop to check for when replica has crashed
    while True:
        try:
            global leader_index
            leader_server = server_docs[leader_index].IP_PORT
            ret_obj = requests.get(f'http://{leader_server}/docList/')
            logger.info(f"docList requested by client: {ret_obj.json()}")
            return ret_obj.json() # return statment acts like a break for the loop
        except Exception as e:
            logger.info(f"Failed to get doc list from leader ({leader_server}), removing dead server from master list and trying again")
            ip_port = leader_server.split(':')
            master_detect_replica_crashed(ip_port[0], ip_port[1])
            continue



### Functions for fault tolerance ###
# Restart token if a timeout is reached
def token_timeout(token: str):
    logger.info(f"token {token} timed out, asking leader to generate a new token for that docID")
    
    global docID_timers
    global token_list
    # remove the token from the token_list and the docID_timers
    token_list.pop(token_list.index(token))
    docID_timers.pop(token, None)
    # Get token info
    docID = token.split(':')[0]
    serial = int(token.split(':')[1])
    serial += 1 #increament serial counter

    # Track and start the new token
    new_token = f"{docID}:{serial}"
    token_list.append(new_token) # Add new token
    docID_timers[new_token] = ResettableTimer(20, token_timeout, new_token)
    docID_timers[new_token].run()

    # NOTE: loop to check for when leader has crashed
    while True:
        try:
            global leader_index
            leader_server = server_docs[leader_index].IP_PORT
            response = requests.post(f"http://{leader_server}/initializeToken/{docID}/{serial}/")
            break
        except Exception as e:
            logger.info(f"Failed to get leader ({leader_server}) to initialize new token, removing dead server from master list and trying again")
            ip_port = leader_server.split(':')
            master_detect_replica_crashed(ip_port[0], ip_port[1])
            continue

# Stopping the timer for this token as it is in use
@app.post("/tokenInUse/{token_id}/{token_serial}/")
def token_in_use(token_id: int, token_serial: int):
    global docID_timers
    token_formatted = f"{token_id}:{token_serial}"
    docID_timers[token_formatted].inUse()
    return {"Message": f"ack for {token_formatted}"}

@app.post("/replicaRecvToken/{token_id}/{token_serial}/")
async def replica_received_token(token_id: int, token_serial: int):
    global docID_timers
    global token_list
    token_formatted = f"{token_id}:{token_serial}"
    if token_formatted in token_list:
        # NOTE: token should always be in the dict (if it isn't then something went very wrong)
        docID_timers[token_formatted].reset()
        return {"Token": f"valid"}
    else:
        return {"Token": f"invalid"}

@app.post("/replicaCrashed/{crashed_ip}/{crashed_port}/")
def replica_crashed(crashed_ip: str, crashed_port: str):
    crashed_ip_port = crashed_ip + ":" + crashed_port
    # find the server with that IP and port
    global server_docs
    servers = [x.IP_PORT for x in server_docs]
    if crashed_ip_port in servers:
        index_dead_server = servers.index(crashed_ip_port)
        server_docs.pop(index_dead_server)
        servers.pop(index_dead_server) # pop server from local copy for leader election
        # update leader (no effect if the popped replica was not the leader)
        global leader_index
        ports = [int(server.split(':')[1]) for server in servers]
        leader_index = ports.index(min(ports))

        logger.info("Popped dead server from list in master")
    
    return {"Message": "ack crash of succesor"}


@app.post("/lostConnection/")
async def transfer_conn(data_str: str = Body()):
    data = json.loads(data_str)

    # Client provide the document they were working with and the IP and PORT they got no response from
    ip = data['IP']
    port = data['PORT']
    docID = int(data['docID'])

    global server_docs

    crashed_ip_port = ip + ':' + port

    servers = [x.IP_PORT for x in server_docs]

    if crashed_ip_port in servers:
        index_dead_server = servers.index(crashed_ip_port)
        server_docs.pop(index_dead_server)
        servers.pop(index_dead_server) # pop server from local copy for leader election
        # update leader (no effect if the popped replica was not the leader)
        global leader_index
        ports = [int(server.split(':')[1]) for server in servers]
        leader_index = ports.index(min(ports))

    if not server_docs:
        return {"Error": "no servers online to connect too"}
    
    # Get server with lowest number of current clients
    index = min(range(len(server_docs)), key=lambda i: server_docs[i].clients_online)
    server_docs[index].clients_online += 1 # Add one more client to this replica

    server = server_docs[index].IP_PORT
    server = str(server).split(':')
    logger.info("Client rerouted to:")
    logger.info(server)

    return {"IP": server[0], "port": server[1]}




### helper functions for the api (not visiable to clients) ###
def master_detect_replica_crashed(crashed_ip: str, crashed_port: str):
    crashed_ip_port = crashed_ip + ":" + crashed_port
    # find the server with that IP and port
    global server_docs
    servers = [x.IP_PORT for x in server_docs]
    if crashed_ip_port in servers:
        index_dead_server = servers.index(crashed_ip_port)
        server_docs.pop(index_dead_server)
        servers.pop(index_dead_server) # pop server from local copy for leader election
        # update leader (no effect if the popped replica was not the leader)
        # NOTE: add print statment to show the leader changing
        global leader_index
        ports = [int(server.split(':')[1]) for server in servers]
        leader_index = ports.index(min(ports))
        logger.info(f"Leader index is {leader_index} and its ip:port are {servers[leader_index]}")

        logger.info("Popped dead server from list in master")