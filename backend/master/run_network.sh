#!/bin/bash

echo "PORT: $1"
export PORT=$1;
export IP="0.0.0.0";
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --port=$PORT --host=$IP