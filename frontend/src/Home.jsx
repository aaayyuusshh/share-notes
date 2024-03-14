import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const Home = () => {
  const [docName, setDocName] = useState("");
  const [docList, setDocList] = useState([]);
  const [idSelected, setIdSelected] = useState("");
  const [nameSelected, setNameSelected] = useState("");

  const handleChange = (e) => setDocName(e.target.value);

  let navigate = useNavigate();

  const navigateToNewDocument = () => {
    console.log(docName)
    fetch('http://127.0.0.1:8000/createDocAndConnect/', {
      method: "POST",
      header: {
        "Content-Type": "application/json",
      },
      body: docName,
    })
    .then((response) => response.json())
    .then((data) => {
      const docID = data.docID.toString()
      const docName = data.docName.toString()
      const IP = data.IP.toString()
      const port = data.port.toString()
      console.log(docID)
      console.log(docName)
      console.log(IP)
      console.log(port)
      // TODO: Pass these variabes as states (or something else, I don't really know JS...) include IP in those variables
      // currently this only connects to 127.0.0.1 (i.e. localhost) 
      navigate(`/document/` + port + '/' + docID + '/' + docName);
    })
    //return // Commented out
  };

  const navigateToExistingDocument = () => {
    console.log(idSelected)
    console.log(nameSelected)
    fetch('http://127.0.0.1:8000/connectToExistingDoc/', {
      method: "POST",
      header: {
        "Content-Type": "application/json",
      },
      body: idSelected,
    })
    .then((response) => response.json())
    .then((data) => {
      const IP = data.IP.toString()
      const port = data.port.toString()
      console.log(IP)
      console.log(port)
      // TODO: Pass these variabes as states (or something else, I don't really know JS...) include IP in those variables
      // currently this only connects to 127.0.0.1 (i.e. localhost) 
      navigate(`/document/` + port + '/' + idSelected + '/' + nameSelected);
    })
  };

  // Get Document List from the server
  const getDocList = async () => {
    const response = await fetch('http://127.0.0.1:8000/docList/')
    setDocList(Object.entries(await response.json()))
  }

  useEffect(() => {
    getDocList()
    console.log(docList)
  }, []);

  return (
    <>
      <div className="homePage">
        <h1>Welcome to Share Notes</h1>
        <input
          type="text"
          placeholder="provide document name..."
          value={docName}
          onChange={handleChange}/>
        <button disabled={!docName} onClick={navigateToNewDocument}>Create New Doc</button>
      </div>
      <div>
        <h2>Document List</h2>
          <select defaultValue=""
            onChange={(e) => {
            console.log(docList[e.target.value][1].id)
            console.log(docList[e.target.value][1].name)
            // Set the id and name of the document user currently selected
            setIdSelected(docList[e.target.value][1].id)
            setNameSelected(docList[e.target.value][1].name)
          }}>
            <option disabled={true} value=""> --Please choose an option-- </option>
            {docList.map(([index, doc]) => {
              return (
                <option key={index} value={index}>
                  {`${doc.id}: ${doc.name}`}
                </option>
              );
            })}
          </select>
        <button disabled={!idSelected} onClick={navigateToExistingDocument}>Open selected document</button>
      </div>
    </>
  );
};

export default Home;