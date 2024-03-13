#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <start_port> <end_port>"
    exit 1
fi

start_port=$1
end_port=$2
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)  # Get the script's directory

# Function to run the command in the current terminal window
run_in_current_terminal() {
    osascript -e "tell application \"Terminal\" to do script \"$1\""
}

for (( port=start_port; port<=end_port; port++ )); do
    echo "Starting server on port: $port"
    echo "cd $script_dir" > /tmp/run_server_$port.sh
    echo "echo 'PORT: $port'" >> /tmp/run_server_$port.sh
    echo "export PORT=$port;" >> /tmp/run_server_$port.sh
    echo "python -m venv venv" >> /tmp/run_server_$port.sh
    echo "source venv/bin/activate" >> /tmp/run_server_$port.sh
    echo "pip install -r requirements.txt" >> /tmp/run_server_$port.sh
    echo "uvicorn server:app --port=\$PORT" >> /tmp/run_server_$port.sh
    chmod +x /tmp/run_server_$port.sh
    run_in_current_terminal "/tmp/run_server_$port.sh"
    sleep 1  # optional delay to ensure the server starts before the next iteration
done

# Run the ../master script in the current terminal window
cd $script_dir/../master && ./run.sh 8000
