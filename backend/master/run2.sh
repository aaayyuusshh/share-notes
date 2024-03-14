python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --port="8000"