# Running natively on python 3.11 + 
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8001
OR:
chmod +x ./run.sh
./run.sh <PORT>
```
# Starting on Remote Master
Set environment variables: PORT, IP, MASTER_IP.

IP should be set to the network IP of this replica connection.
MASTER_IP should be the network IP of the master connection.
PORT should be the port number.
Then run server using this following command:
uvicorn server:app --port 8001 --host=0.0.0.0