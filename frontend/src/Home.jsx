import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const Home = () => {
  const [docName, setDocName] = useState("");
  const [docList, setDocList] = useState([]);
  const [idSelected, setIdSelected] = useState("");
  const [nameSelected, setNameSelected] = useState("");
  const [searchTerm, setSearchTerm] = useState('');

  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
  };

  const filteredDocList = docList.filter(([index, doc]) =>
    doc.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleChange = (e) => setDocName(e.target.value);

  let navigate = useNavigate();

  const navigateToNewDocument = () => {
    console.log(docName)
    fetch('http://127.0.0.1:8000/newDocID/', {
      method: "POST",
      header: {
        "Content-Type": "application/json",
      },
      body: docName,
    })
    .then((response) => response.json())
    .then((data) => {
      console.log(data.port.toString())
      console.log(data.docID.toString())
      const port = data.port.toString()
      const docID = data.docID.toString()
      console.log(docID)
      console.log(docName)
      navigate(`/document/` + port + '/' + docID + '/' + docName);
    })
    return
  };

  const navigateToExistingDocument = () => {
    // TODO: Hard coded port of 8001, it should instead ask the master what port to use
    navigate(`/document/8001/` + idSelected + '/' + nameSelected);
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
    <div className="homePage" style={{ textAlign: 'center', padding: '20px', backgroundColor: '#f0f0f0' }}>
      <h1 style={{ color: '#333' }}>Welcome to Share Notes</h1>
      <input
        type="text"
        placeholder="Provide a new document name..."
        value={docName}
        onChange={handleChange}
        style={{ padding: '8px', margin: '10px', width: '60%', borderRadius: '4px', border: '1px solid #ccc' }}
      />
      <button
        disabled={!docName}
        onClick={navigateToNewDocument}
        style={{
          padding: '8px 15px',
          backgroundColor: '#4CAF50',
          color: 'white',
          border: 'none',
          borderRadius: '20px',
          cursor: 'pointer',
        }}
      >
        Create New Doc
      </button>
    </div>
    <div style={{ textAlign: 'center', marginTop: '20px' }}>
      <h2 style={{ color: '#333' }}>Document List</h2>
      <input
        type="text"
        placeholder="Search by document name..."
        value={searchTerm}
        onChange={handleSearchChange}
        style={{
          padding: '8px',
          margin: '10px',
          width: '60%',
          borderRadius: '4px',
          border: '1px solid #ccc',
        }}
      />
      <div
        style={{
          height: '40vh',
          overflowY: 'auto',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          {filteredDocList.map(([index, doc], i) => (
            <button
              key={index}
              onClick={() => {
                setIdSelected(doc.id);
                setNameSelected(doc.name);
              }}
              style={{
                width: '60%',
                padding: '15px',
                backgroundColor: i % 2 === 0 ? 'white' : '#f0f0f0',
                border: 'none',
                borderRadius: '8px',
                marginBottom: '5px',
                cursor: 'pointer',
                outline: 'none',
                transition: 'background-color 0.3s ease-in-out',
                ...(idSelected === doc.id && { backgroundColor: '#4285F4', color: 'white' }),
              }}
            >
              {`${doc.id}: ${doc.name}`}
            </button>
          ))}
        </div>
      </div>
      <button
        disabled={!idSelected}
        onClick={navigateToExistingDocument}
        style={{
          padding: '8px 15px',
          marginTop: '20px',
          backgroundColor: '#4285F4',
          color: 'white',
          border: 'none',
          borderRadius: '20px',
          cursor: 'pointer',
        }}
      >
        Open Selected Document
      </button>
    </div>
  </>
  );  
  
};

export default Home;