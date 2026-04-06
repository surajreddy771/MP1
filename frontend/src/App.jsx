import { useState, useEffect } from "react";
import Dashboard from "./pages/Dashboard";
import Attendance from "./pages/Attendance";
import Enroll from "./pages/Enroll";
import Alerts from "./pages/Alerts";
import "./index.css";

const NAV = [
  { id: "dashboard", label: "Overview" },
  { id: "attendance", label: "Attendance" },
  { id: "enroll", label: "Enroll" },
  { id: "alerts", label: "SMS Alerts" },
];

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [online, setOnline] = useState(false);
  const [recRunning, setRecRunning] = useState(false);

  useEffect(() => {
    const check = () => {
      fetch("http://localhost:8000/health")
        .then(() => setOnline(true))
        .catch(() => setOnline(false));
      fetch("http://localhost:8000/face/status")
        .then(r => r.json())
        .then(d => setRecRunning(d.running))
        .catch(() => {});
    };
    check();
    const id = setInterval(check, 8000);
    return () => clearInterval(id);
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
          {NAV.map(n => (
            <button key={n.id}
              className={`nav-btn${page === n.id ? " active" : ""}`}
              onClick={() => setPage(n.id)}>
              {n.label}
            </button>
          ))}
        </nav>
        <div className="header-status">
          {recRunning && <><span className="live-dot" /><span className="status-label" style={{color:"var(--accent)"}}>REC</span><span style={{margin:"0 10px",color:"var(--border-hi)"}}>|</span></>}
          <span className={`status-dot ${online ? "online" : "offline"}`} />
          <span className="status-label">{online ? "API Online" : "API Offline"}</span>
        </div>
      </header>
      <main className="main">
        {page === "dashboard"  && <Dashboard />}
        {page === "attendance" && <Attendance />}
        {page === "enroll"     && <Enroll setRecRunning={setRecRunning} recRunning={recRunning} />}
        {page === "alerts"     && <Alerts />}
      </main>
    </div>
  );
}