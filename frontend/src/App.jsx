import { useState, useEffect } from "react";
import Dashboard from "./pages/Dashboard";
import Attendance from "./pages/Attendance";
import Enroll from "./pages/Enroll";
import "./index.css";

const NAV = [
  { id: "dashboard", label: "Overview" },
  { id: "attendance", label: "Attendance" },
  { id: "enroll", label: "Enroll" },
];

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [online, setOnline] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/health")
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <span className="brand-icon" />
          <span className="brand-name">FaceTrack</span>
          <span className="brand-version">v1.0</span>
        </div>
        <nav className="header-nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`nav-btn${page === n.id ? " active" : ""}`}
              onClick={() => setPage(n.id)}
            >
              {n.label}
            </button>
          ))}
        </nav>
        <div className="header-status">
          <span className={`status-dot ${online ? "online" : "offline"}`} />
          <span className="status-label">{online ? "API Online" : "API Offline"}</span>
        </div>
      </header>

      <main className="main">
        {page === "dashboard" && <Dashboard />}
        {page === "attendance" && <Attendance />}
        {page === "enroll" && <Enroll />}
      </main>
    </div>
  );
}