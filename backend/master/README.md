# Running natively on python 3.11 + 
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload

# go to the <url>/docs