import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { dismissBootSplash } from "./lib/bootSplash";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
dismissBootSplash();
