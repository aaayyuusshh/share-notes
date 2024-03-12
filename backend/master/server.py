from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional, Annotated, List, Any
import requests
#import aiohttp  NOTE: The 'requests' module is not asyncronous, this one is ... I am not sure if being sychornous will issues
import logging
from sqlmodel import Field, SQLModel

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

@app.post("/newDocID/")
async def create_docID(docName: str = Body()):
    # This should ideally be passed as 'data=' parameter in the post request, but it causes issues with the naming
    ret_obj = requests.post(f'http://127.0.0.1:8001/newDocID/{docName}')
    logger.info(ret_obj.json())
    return ret_obj.json()

@app.get("/docList/")
def doc_list() -> Any:
    ret_obj = requests.get('http://127.0.0.1:8001/docList/')
    logger.info(ret_obj.json())
    return ret_obj.json()
