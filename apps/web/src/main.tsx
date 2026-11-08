import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import { App } from "./App";
import "./index.css";

// Service worker : mise à jour automatique du shell applicatif, fonctionnement hors ligne.
registerSW({ immediate: true });

// Demande un stockage persistant pour éviter l'éviction des données personnelles par le navigateur.
void navigator.storage?.persist?.();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
