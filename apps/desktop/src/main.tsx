import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { revealMainWindow } from "./lib/revealWindow";

void revealMainWindow();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
