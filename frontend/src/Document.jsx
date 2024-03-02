import React, { useState, useEffect, useRef } from 'react';
import './App.css';

export default function Document() {
  const [textValue, setTextValue] = useState("");
  const ws = useRef(null);

  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/ws/1');
    ws.current.onopen = () => {
      console.log('WebSocket Connected');
    };
    ws.current.onmessage = (event) => {
      console.log('Message from server ', event.data);
      setTextValue(event.data);
    };
    ws.current.onclose = () => console.log('WebSocket Disconnected');
    return () => {
      if (ws.current) {
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
        <h2 className="logoText">📕 Document</h2>
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
