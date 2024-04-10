import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const Home = () => {
  const [docName, setDocName] = useState("");
  const [docList, setDocList] = useState([]);
  const [idSelected, setIdSelected] = useState("");
  const [nameSelected, setNameSelected] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  const MASTER_IP = "localhost";

  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
  };

  const filteredDocList = docList.filter(([index, doc]) =>
    doc.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleChange = (e) => setDocName(e.target.value);

  let navigate = useNavigate();

  const navigateToNewDocument = () => {
    console.log(docName);
    fetch("http://" + MASTER_IP + ":8000/createDocAndConnect/", {
      method: "POST",
      header: {
        "Content-Type": "application/json",
      },
      body: docName,
    })
      .then((response) => response.json())
      .then((data) => {
        const docID = data.docID.toString();
        const docName = data.docName.toString();
        const IP = data.IP.toString();
        const port = data.port.toString();
        console.log(docID);
        console.log(docName);
        console.log(IP);
        console.log(port);
        navigate(`/document/` + IP + "/" + port + "/" + docID + "/" + docName);
      });
  };

  const navigateToExistingDocument = () => {
    console.log(idSelected);
    console.log(nameSelected);
    fetch("http://" + MASTER_IP + ":8000/connectToExistingDoc/", {
      method: "POST",
      header: {
        "Content-Type": "application/json",
      },
    })
      .then((response) => response.json())
      .then((data) => {
        const IP = data.IP.toString();
        const port = data.port.toString();
        console.log(IP);
        console.log(port);
        navigate(
          `/document/` + IP + "/" + port + "/" + idSelected + "/" + nameSelected
        );
      });
  };

  // Get Document List from the server
  const getDocList = async () => {
    const response = await fetch("http://" + MASTER_IP + ":8000/docList/");
    setDocList(Object.entries(await response.json()));
    console.log(response);
  };

  useEffect(() => {
    getDocList();
  }, []);

  return (
    <>
      <div
        className="homePage"
        style={{
          textAlign: "center",
          backgroundColor: "#f0f0f0",
        }}
      >
        <h1 style={{ color: "#333" }}>
          Welcome to <span className="titleText1">share</span><span className="titleText2">notes</span> 📁
        </h1>
        <input
          type="text"
          placeholder="Provide a new document name..."
          value={docName}
          onChange={handleChange}
          style={{
            padding: "8px",
            margin: "10px",
            width: "60%",
            borderRadius: "4px",
            border: "1px solid #ccc",
          }}
        />
        <button
          className="createDocButton"
          disabled={!docName}
          onClick={navigateToNewDocument}>
          Create New Doc
        </button>
      </div>
      <div className="documentList"style={{ textAlign: "center", marginTop: "30px", display: "flex", flexDirection: "column", alignItems: "center"}}>
        <h2 style={{ color: "#333" }}>Document List</h2>
        <input
          type="text"
          placeholder="🔍  Search by document name..."
          value={searchTerm}
          onChange={handleSearchChange}
          style={{
            padding: "8px",
            margin: "10px",
            width: "60%",
            borderRadius: "20px",
            border: "1px solid #ccc",
          }}
        />
        <div
          style={{
            height: "50vh",
            overflowY: "auto",
            width: "60%",
            borderBottom: "1px solid #e1dfdf",
            
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            {filteredDocList.length === 0? (
              <div>
                <img className="emptyListImg" src="https://cdn-icons-png.flaticon.com/512/7486/7486744.png" alt="" />
                <p className="emptyListTitle">Document list is currently empty</p>
                <p className="emptyListText">Create a new doc above to add it to the document list.</p>
              </div>
              ) : (
                filteredDocList.map(([index, doc], i) => (
                <button
                  key={index}
                  onClick={() => {
                    setIdSelected(doc.id);
                    setNameSelected(doc.name);
                  }}
                  style={{
                    width: "60%",
                    padding: "15px",
                    backgroundColor: i % 2 === 0 ? "white" : "#f0f0f0",
                    border: "none",
                    borderRadius: "8px",
                    marginBottom: "5px",
                    cursor: "pointer",
                    outline: "none",
                    transition: "background-color 0.3s ease-in-out",
                    ...(idSelected === doc.id && {
                      backgroundColor: "#4285F4",
                      color: "white",
                    }),
                  }}
                >
                {`${doc.id}: ${doc.name}`}
                </button>
              ))
            )}
          </div>
        </div>
        <button
          className="openDocButton"
          disabled={!idSelected}
          onClick={navigateToExistingDocument}>
          Open Selected Document
        </button>
      </div>
    </>
  );
};

export default Home;
