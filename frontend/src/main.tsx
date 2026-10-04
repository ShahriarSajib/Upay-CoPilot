import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { CopilotProvider } from "./data/store";
import { AuthProvider } from "./data/auth";
import "./index.css";

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <CopilotProvider>
          <App />
        </CopilotProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);