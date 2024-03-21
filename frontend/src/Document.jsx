import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useParams } from "react-router-dom";
import './App.css';

export default function Document() {
  const [textValue, setTextValue] = useState("");
  //const ws = useRef(null);
  const MASTER_IP = "localhost"


  const [canEdit, setCanEdit] = useState(false);

  const { ip, port, id, docName } = useParams()

  const [webSocket, setWebSocket] = useState(null);


  useEffect(() => {
    connectWebSocket(ip, port);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectWebSocket = (ip, port) => {
    const ws = new WebSocket('ws://' + ip + ':' + port + '/ws/' + id + '/' + docName);

    ws.onopen = () => {
      console.log('WebSocket Connected');
    };
    ws.onmessage = (event) => {
      console.log('Message from server ', event.data);
      // split event.data into doc content and IP
      const indexOfFirstColon = event.data.indexOf(':');
      const ip_received = event.data.substring(0, indexOfFirstColon);
      console.log(ip_received===ip);
      // check IP value sent to server
      // if IP is different change TextValue
      // if (ip_received !== ip) {
      //   setTextValue(event.data.substring(indexOfFirstColon + 1));
      // }

      setTextValue(event.data.substring(indexOfFirstColon + 1));

    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      requestNewIPAndPort(ip, port);
    };

    setWebSocket(ws);
  };

  const requestNewIPAndPort = (ip, port) => {
    const bodyObj = JSON.stringify({
      IP: ip,
      PORT: port,
      docID: id
    })
    console.log(bodyObj)
    try {
      fetch('http://'+ MASTER_IP +':8000/lostConnection/', {
        method: "POST",
        header: {
          'Accept': 'application/json',
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          IP: ip,
          PORT: port,
          docID: id,
        })
      })
      .then((response) => response.json())
      .then((data) => {
      const IP = data.IP.toString()
      const PORT = data.port.toString()
      console.log(IP)
      console.log(PORT)
      if (IP && PORT) {
        reconnectWebSocket(IP, PORT);
      } else {
        console.error('Failed to get new IP and port');
      }
    })
    } catch (error) {
      console.error('Error fetching new IP and port:', error);
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
    setCanEdit(true);

    fetch(`http://${ip}:${port}/startEdit/`, {
      method: "POST",
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        docID: id,
      }),
    })
    .then(response => response.json())
    .then(data => {
      console.log('Success:', data);
    })
    .catch((error) => {
      console.error('Error:', error);
    });
  };

  function handleUpdate(event) {
    const { value } = event.target;
    setTextValue(value);

    // Send textValue if the ws is open
    if (webSocket && webSocket.readyState === WebSocket.OPEN) {
      webSocket.send(JSON.stringify({ content: value, ip: ip }));
    }
  }

  return (
    <div className="mainContainer">
      <nav className="navBar">
        <h2 className="logoText">📕 {docName}</h2>
      </nav>
      <div className="textContainer">
        <div className="container">
          <label htmlFor="textArea" className="textLabel">Your Document</label>
          {!canEdit && (
            <button onClick={handleStartEditing} className="editButton">Start Editing</button>
          )}
          <textarea
            className="textArea"
            id="textArea"
            cols="90"
            rows="32"
            placeholder="Start typing your document..."
            value={textValue}
            onChange={handleUpdate}
            disabled={!canEdit}
          />
        </div>
      </div>
    </div>
  );
}