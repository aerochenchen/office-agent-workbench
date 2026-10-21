import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const userAgent = navigator.userAgent;
document.documentElement.dataset.platform = /Windows/i.test(userAgent)
  ? "windows"
  : /Mac/i.test(userAgent)
    ? "mac"
    : "other";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
