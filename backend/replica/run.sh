#!/bin/bash

echo "PORT: $1"
export PORT=$1;
uvicorn server:app --port=$PORT