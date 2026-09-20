import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initApi } from "./api";
import App from "./App";
import "./styles/index.css";

const root = createRoot(document.getElementById("root")!);

initApi()
  .then(() => {
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  })
  .catch((e: Error) => {
    // Configuration errors surface here, before any route renders.
    root.render(<pre style={{ padding: 24, color: "#b42318", whiteSpace: "pre-wrap", fontFamily: "ui-monospace, monospace" }}>{e.message}</pre>);
  });
