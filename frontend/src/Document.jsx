import React, { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useParams } from "react-router-dom";
import "./App.css";

export default function Document() {
  const [textValue, setTextValue] = useState("");

  const MASTER_IP = "10.13.67.149";

  const { ip, port, id, docName } = useParams();

  const [webSocket, setWebSocket] = useState(null);

  const [canEdit, setCanEdit] = useState(false);

  const [isLoading, setIsLoading] = useState(false);

  const [isReconnecting, setIsReconnecting] = useState(false);

  const CAN_EDIT = useRef(canEdit);

  let navigate = useNavigate();
  useEffect(() => {
    connectWebSocket(ip, port);
    CAN_EDIT.current = canEdit;
  }, []);

  const connectWebSocket = (ip, port) => {
    // Sending 'canEdit' will be false in everycase except when the client was editing and lost connection
    // In that case, the canEdit flag is used to tell the replica to generate a new token and make sure this client gets
    // first access to continue editing seamlessly
    console.log(
      "connect to websocket: " +
        ip +
        ":" +
        port +
        "/ws/" +
        id +
        "/" +
        docName +
        "/" +
        CAN_EDIT.current +
        "/"
    );
    const ws = new WebSocket(
      "ws://" +
        ip +
        ":" +
        port +
        "/ws/" +
        id +
        "/" +
        docName +
        "/" +
        CAN_EDIT.current +
        "/"
    );

    ws.onopen = () => {
      console.log("WebSocket Connected");
    };
    ws.onmessage = (event) => {
      console.log("Message from server ", event.data);
      console.log("CAN_EDIT.current status: " + CAN_EDIT.current)
      setIsReconnecting(false);

      if (event.data === "*** START EDITING ***") {
        setIsLoading(false);
        CAN_EDIT.current = true;
        console.log("CAN_EDIT.current " + CAN_EDIT.current);

        setCanEdit(true);
        // console.log("canEdit textbox " + canEdit);

      } else if (!CAN_EDIT.current) {
        console.log("Updating textbox as this user is not editing")
        setTextValue(event.data);
      }
      // Shouldn't need this as only once client can update
      //setTextValue(event.data);
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      setIsLoading(true);

      setIsReconnecting(true); // used to gray out the textbox

      requestNewIPAndPort(ip, port);
    };

    setWebSocket(ws);
  };

  const requestNewIPAndPort = (ip, port) => {
    const bodyObj = JSON.stringify({
      IP: ip,
      PORT: port,
      docID: id,
    });
    console.log(bodyObj);
    try {
      fetch("http://" + MASTER_IP + ":8000/lostConnection/", {
        method: "POST",
        header: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          IP: ip,
          PORT: port,
          docID: id,
        }),
      })
        .then((response) => response.json())
        .then((data) => {
          const IP = data.IP.toString();
          const PORT = data.port.toString();
          console.log(IP);
          console.log(PORT);
          if (IP && PORT) {
            reconnectWebSocket(IP, PORT);
          } else {
            console.error("Failed to get new IP and port");
          }
        });
    } catch (error) {
      console.error("Error fetching new IP and port:", error);
    }
  };

  const reconnectWebSocket = (IP, PORT) => {
    // Close the previous WebSocket connection
    if (webSocket) {
      webSocket.close();
    }
    // Establish a new WebSocket connection with the new IP and port
    connectWebSocket(IP, PORT);
  };

  const handleStartEditing = () => {
    setIsLoading(true);
    //NOTE: On the server side, any message sent is interpreted as a request to edit
    webSocket.send(JSON.stringify({ startEdit: true }));
  };

  const handleStopEditing = () => {
    setCanEdit(false);
    CAN_EDIT.current = false;
    console.log("CAN_EDIT.current after handleStopEditing: " + CAN_EDIT.current);
    webSocket.send(JSON.stringify({ content: "*** STOP EDITING ***" }));
  };

  function handleUpdate(event) {
    const { value } = event.target;
    setTextValue(value);

    // Send textValue if the ws is open
    if (webSocket && webSocket.readyState === WebSocket.OPEN) {
      webSocket.send(JSON.stringify({ content: value }));
    }
  }

  function navigateHome() {
    navigate(`/`);
  }

  return (
    <div className="rootContainer">
      <nav
        className="navBar"
      >
        <button
          onClick={navigateHome}
          style={{
            backgroundColor: "#333",
            border: "none",
            marginRight: "10px",
          }}
        >

          <p className="logo" title="sharenotes home">📁</p>
        </button>
        <h2 className="docName" style={{ marginTop: "8px" }}>{docName}</h2>
      </nav>
      <div className="main">
        <div className="container" style={{ border: "none", padding: "15px" }}>
          {!canEdit && (
            <>
              {isLoading ? (
                <button className="btn"
                  style={{
                    color: "black",
                    border: "none",
                    padding: "5px 12px",
                    cursor: "pointer",
                    borderRadius: "20px",
                  }}
                >
                  Loading...
                </button>
              ) : (
                <button className="btn"
                  style={{
                    backgroundColor: "#4CAF50",
                    color: "#fff",
                    border: "none",
                    padding: "5px 12px",
                    cursor: "pointer",
                    borderRadius: "20px",
                  }}
                  onClick={handleStartEditing}
                >
                  Start Editing
                </button>
              )}
            </>
          )}
          {canEdit && (
            <>
              <button className="btn"
                style={{
                  backgroundColor: "#ff0040",
                  color: "#fff",
                  border: "none",
                  padding: "5px 12px",
                  cursor: "pointer",
                  borderRadius: "20px",
                }}
                onClick={handleStopEditing}
              >
                Stop Editing
              </button>
            </>
          )}
          <textarea
            style={{
              height: "100%",
              width: "95%",
              padding: "10px",
              marginTop: "10px",
              border: "1px solid #ccc",
              borderRadius: "5px",
              resize: "none",
              backgroundColor: "white",
              overflow: "hidden"
            }}
            id="textArea"
            cols="200"
            rows="25"
            placeholder="Start typing your document..."
            value={textValue}
            onChange={handleUpdate}
            disabled={!canEdit || isReconnecting}
         />
          <p className="btn">{textValue.length} Characters</p>
        </div>
      </div>
    </div>
  );
}
