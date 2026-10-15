import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ServicePage } from "./pages/ServicePage";
import { LiveServicePage } from "./pages/LiveServicePage";
import { AdminPage } from "./pages/AdminPage";
import "./styles/base.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {window.location.pathname === "/service-preview" ? (
      <ServicePage />
    ) : window.location.pathname === "/experience" ? (
      <LiveServicePage />
    ) : (
      <AdminPage />
    )}
  </StrictMode>,
);
