import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/index.css";

const root = createRoot(document.getElementById("root")!);

/**
 * Boot in order: read and validate the configuration, build the API client, then load the app.
 *
 * The app's modules read `env` at their top level, so they are imported only after `loadEnv()`
 * succeeded: a bad or missing configuration is rendered as a readable message here, never thrown
 * from the module loader into a blank page.
 */
async function boot() {
  const { loadEnv } = await import("./config/env");
  loadEnv();
  const { initApi } = await import("./api");
  await initApi();
  const { default: App } = await import("./App");
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

boot().catch((e: unknown) => {
  // Configuration errors surface here, before any route renders.
  const message = e instanceof Error ? e.message : String(e);
  root.render(
    <pre role="alert" data-config-error style={{ padding: 24, color: "#b42318", whiteSpace: "pre-wrap", fontFamily: "ui-monospace, monospace" }}>
      {message}
    </pre>,
  );
});
