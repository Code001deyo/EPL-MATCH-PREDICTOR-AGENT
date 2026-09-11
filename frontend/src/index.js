import React from "react";
import ReactDOM from "react-dom/client";
// Before App, so the interceptor is installed before anything can request.
import "./api";
import App from "./App";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<React.StrictMode><App /></React.StrictMode>);
