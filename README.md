# sharenotes 📚🚀

<img width="1438" alt="Screen Shot 2024-04-11 at 12 43 49 AM" src="https://github.com/aaayyuusshh/share-notes/assets/80851741/d007d964-e9d0-480c-bcce-3c2cc535f2a0">
<img width="1438" alt="Screen Shot 2024-04-11 at 12 45 34 AM" src="https://github.com/aaayyuusshh/share-notes/assets/80851741/4f45f4c7-1c7b-4999-afa2-d185e7a91258">


# Start Instructions

Running this application using the following instructions requires a MacOS or Linux machine.

## First start the Backend 🏗️

To start the backend, we must start the master server first.

Navigate to the `backend/master` directory and execute the following command to run locally:

```bash
./run_local.sh 8000
```

To start the replica servers, navigate to the `backend/replica` directory and execute the following commands:

```bash
./start_replica_local.sh 8001
```
These commands run the master backend server on port 8000 and replication servers on port 8001. More replica servers can be started using the above command with different port number.

## Running the Frontend 🌐
To run the frontend, navigate to the frontend directory and run the following commands. Also ensure the `MASTER_IP` variable in the `Home.jsx` and `Document.jsx` components is set to `localhost`.

```bash
npm install
npm run dev
```

