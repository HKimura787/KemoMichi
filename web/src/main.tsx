import React from "react";
import ReactDOM from "react-dom/client";
import "@digital-go-jp/design-tokens/dist/tokens.css";
import "./styles.css";
import { App } from "./App";
import { I18nProvider } from "./i18n";
import { ToastProvider } from "./ui";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </I18nProvider>
  </React.StrictMode>,
);
