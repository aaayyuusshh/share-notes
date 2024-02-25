import './App.css'
import {React, useState, useEffect} from 'react'

export default function App() {
  const [textValue, setTextValue] = useState("");
  const [chunks, setChunks] = useState([]);

  useEffect(() => {
    handleChunks();
  },[textValue]);

  function handleUpdate(event) {
      setTextValue(event.target.value);
  }

  //handle document text data, chunk by chunk
  function handleChunks() {
    const chunkSize = 3;
    const chunksArray = [];
    for(let i=0; i<textValue.length; i+=chunkSize) {
      chunksArray.push(textValue.substring(i, i+chunkSize));
    }
    setChunks(chunksArray);
    console.log(chunksArray)
  }

  return (
    <div className="mainContainer">
      <nav className="navBar">
        <h2 className="logoText">📕 share-note.</h2>
      </nav>
      <div className="textContainer">
        <div className="container">
          <label className="textLabel" htmlFor="textArea">Document 1</label>
            <textarea 
              className="textArea" name="postContent" id="textArea" cols="90" rows="32" placeholder="start your document...."
              value={textValue} 
              onChange={handleUpdate}>
            </textarea>
        </div>
      </div>
    </div>
  )
}
