import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import './App.css';

export default function Document() {
  const [textValue, setTextValue] = useState("");
  const ws = useRef(null);

  // get document name provided via router-dom functionality
  const location = useLocation();
  let docName = location.state.docName;

  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/ws');
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

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
