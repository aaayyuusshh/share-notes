import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useParams } from "react-router-dom";
import './App.css';

export default function Document() {
  const [textValue, setTextValue] = useState("");
  const ws = useRef(null);

  const { port, id, docName } = useParams()

  useEffect(() => {
    // The port is passed as a paramter in the URL, ideally it would not be shown to the user (currently not transparent)
    ws.current = new WebSocket('ws://localhost:' + port + '/ws/' + id + '/' + docName);
    ws.current.onopen = () => {
      console.log('WebSocket Connected');
    };
    ws.current.onmessage = (event) => {
      console.log('Message from server ', event.data);
      setTextValue(event.data);
    };
    ws.current.onclose = () => console.log('WebSocket Disconnected');
    return () => {
      if (!ws.current) {
        ws.current.close();
      }
    };
  }, []);

  function handleUpdate(event) {
    const { value } = event.target;
    setTextValue(value);

    // Send textValue if the ws is open
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ content: value }));
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
          <textarea
            className="textArea"
            id="textArea"
            cols="90"
            rows="32"
            placeholder="Start typing your document..."
            value={textValue}
            onChange={handleUpdate}
          />
        </div>
      </div>
    </div>
  );
}

// function to handle updates line by line (was overwritten in main branch had a copy in my local branch -Dvij)
/*
  function handleUpdate(event) {
    const { value, selectionStart } = event.target;
    setTextValue(value);

    // Calculate the current line number and data
    const lines = value.substr(0, selectionStart).split('\n');
    const lineNumber = lines.length;
    const currentLineData = lines[lines.length - 1] + value.substr(selectionStart).split('\n')[0];

    console.log(`Line Number: ${lineNumber}, Line Data: '${currentLineData}'`);

    // Send the line number and data if the WebSocket connection is open
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ line: lineNumber, data: currentLineData }));
    }
  }
*/