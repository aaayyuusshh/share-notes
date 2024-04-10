# Running natively on python 3.11 + 
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```
# Running master server on network
Run server on 0.0.0.0 and record MASTER_IP connection.