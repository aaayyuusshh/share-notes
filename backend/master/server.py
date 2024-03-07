from fastapi import Depends, Body, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# Create an instance of the FastAPI class
app = FastAPI(title="Master Server")

# Dependency
def common_parameters(q: Optional[str] = None):
    return {"q": q}

# Routes
@app.get("/")
async def read_root():
    return {"Hello": "World"}
