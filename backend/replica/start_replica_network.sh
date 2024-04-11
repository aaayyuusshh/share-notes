#!/bin/bash

echo "PORT: $1"
export PORT=$1;
# enter the IP address of network connection for the replica
export IP="10.13.67.149";
# enter the IP address of network connection for the master server
export MASTER_IP="10.13.67.149";
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --port=$PORT --host="0.0.0.0"