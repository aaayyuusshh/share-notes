import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const Home = () => {
  const [docName, setDocName] = useState("");
  const handleChange = (e) => setDocName(e.target.value);

  let navigate = useNavigate();

  const navigateToNewDocument = () => {
    navigate(`/document`, { 
      state: {
        docName: docName
      }
    });
  };

  const navigateToExistingDocument = () => {
    navigate('/document_list');
  };

  return (
    <div className="homePage">
      <h1>Welcome</h1>
      <input
        type="text"
        placeholder="provide document name..."
        value={docName}
        onChange={handleChange}/>
      <button disabled={!docName} onClick={navigateToNewDocument}>Create New Doc</button>
      <button onClick={navigateToExistingDocument}>Link to Existing Document</button>
    </div>
  );
};

export default Home;
