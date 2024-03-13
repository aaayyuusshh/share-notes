#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <start_port> <end_port>"
    exit 1
fi

start_port=$1
end_port=$2

for (( port=start_port; port<=end_port; port++ )); do
    echo "Killing processes on port: $port"
    lsof -ti :$port | xargs kill -9
done
