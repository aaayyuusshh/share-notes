# Share Notes 📚🚀

## Running the Backend 🏗️

To start the backend server, navigate to the `backend/replica` directory and execute the following commands:

```bash
cd backend/replica
./run.sh 8001 8005
```
This command sets up and runs the master backend server on port 8000 and replication servers on ports 8001 to 8005.

## Running the Frontend 🌐
To run the frontend, navigate to the frontend directory and run the following commands:

```bash
cd frontend
npm install
npm run dev
```
These commands install the necessary dependencies and start the development server for the frontend.


For fault tolerance demo:

Start master using:

./run_local.sh 8000

Start replicas using:

./start_replica_local.sh 8002
./start_replica_local.sh 8003

Start frontend using:

npm run dev