import './App.css'
import {useState, React} from 'react'

export default function App() {

  const [textValue, setTextValue] = useState("");

  function handleUpdate(event) {
      setTextValue(event.target.value)
  }

  return (
    <div class="container mainContainer">
      <nav class="navBar">
        <h1>📕 share-note.</h1>
      </nav>
      <div>
        <label htmlFor="textArea">Type Below</label>
        <textarea 
          className="textArea" name="postContent" id="textArea" cols="150" rows="32" placeholder="start your document...."
          value={textValue} 
          onChange={handleUpdate}>
        </textarea>
      </div>
    </div>
  )
}
