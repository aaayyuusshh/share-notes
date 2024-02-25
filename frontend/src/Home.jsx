import React from "react";
import { useNavigate } from "react-router-dom";

const Home = () => {
  let navigate = useNavigate();

  const navigateToNewDocument = () => {
    navigate(`/document`);
  };

  const navigateToExistingDocument = () => {
    // implement logic
}

  return (
    <div>
      <h1>Welcome</h1>
      <button onClick={navigateToNewDocument}>New Document</button>
      <button onClick={navigateToExistingDocument}>Link to Existing Document</button>
    </div>
  );
};

export default Home;
