# Running on a Docker Container
docker build -t share-note-server .

# Run multiple containers
docker run -p 8000:8001 share-note-server
docker run -p 8000:8002 share-note-server


# Running natively on python 3.11 + 
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload

# go to the <url>/docs