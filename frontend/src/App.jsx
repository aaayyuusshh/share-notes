import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Document from "./Document";
import Home from "./Home";

export default function App() {
  return (
    <Router>
      <div>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/document/:port/:id/:docName" element={<Document />} />
        </Routes>
      </div>
    </Router>
  );
}