import { useEffect, useState } from "react";

const API = "http://localhost:8000";

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export default function Attendance() {
  const today = new Date().toISOString().slice(0, 10);

  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  const [search, setSearch] = useState("");

  const load = () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    params.set("limit", "500");

    fetch(`${API}/attendance?${params}`)
      .then((r) => r.json())
      .then((data) => { setRecords(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleExport = () => {
    const params = new URLSearchParams();
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo)   params.set("date_to", dateTo);
    window.open(`${API}/attendance/export?${params}`, "_blank");
  };

  const filtered = records.filter((r) =>
    !search || r.user_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="page-title">Attendance log</div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="input-label">From</label>
            <input
              type="date" className="input" style={{ width: 150 }}
              value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="input-label">To</label>
            <input
              type="date" className="input" style={{ width: 150 }}
              value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 180 }}>
            <label className="input-label">Search name</label>
            <input
              className="input" placeholder="Filter by name..."
              value={search} onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button className="btn btn-primary" onClick={load} disabled={loading}>
            {loading ? "Loading…" : "Apply"}
          </button>
          <button className="btn btn-ghost" onClick={handleExport}>
            Export CSV
          </button>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          {filtered.length} record{filtered.length !== 1 ? "s" : ""}
        </div>
        <div className="table-wrap">
          {loading ? (
            <div className="loading">Loading records…</div>
          ) : filtered.length === 0 ? (
            <div className="empty-state">No records found</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Camera</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id}>
                    <td className="name">{r.user_name}</td>
                    <td className="mono">{r.session_date}</td>
                    <td className="mono">{fmtTime(r.timestamp)}</td>
                    <td>
                      {r.is_late
                        ? <span className="badge late">Late</span>
                        : <span className="badge present">Present</span>
                      }
                    </td>
                    <td className="mono">
                      {r.confidence != null ? `${r.confidence}%` : "—"}
                    </td>
                    <td className="mono">{r.camera_id || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}