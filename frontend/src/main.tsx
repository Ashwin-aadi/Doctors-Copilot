import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/globals.css";
import { App } from "./app/App";
import { initI18n } from "./lib/i18n";

async function bootstrap() {
  const lang = await initI18n();
  document.documentElement.lang = lang;

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
