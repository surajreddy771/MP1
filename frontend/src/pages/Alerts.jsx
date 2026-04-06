import { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function Alerts() {
  const [rates, setRates]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [threshold, setThreshold] = useState(75);
  const [dateFrom, setDateFrom]   = useState("");
  const [dateTo, setDateTo]       = useState("");
  const [sending, setSending]     = useState(false);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState("");

  const loadRates = () => {
    setLoading(true);
    const p = new URLSearchParams();
    if (dateFrom) p.set("date_from", dateFrom);
    if (dateTo)   p.set("date_to",   dateTo);
    fetch(`${API}/stats/rates?${p}`)
      .then(r => r.json())
      .then(d => { setRates(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadRates(); }, []);

  const below = rates.filter(r => r.rate < threshold);
  const noPhone = below.filter(r => !r.phone);

  const handleSend = async (dry) => {
    setSending(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}/sms/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threshold, date_from: dateFrom || null, date_to: dateTo || null, dry_run: dry }),
      });
      const d = await res.json();
      if (!res.ok) setError(d.detail || "Failed.");
      else setResult({ ...d, dry });
    } catch { setError("Cannot reach API."); }
    setSending(false);
  };

  const rateColor = (r) => r < 50 ? "var(--danger)" : r < 75 ? "var(--warn)" : "var(--accent)";

  return (
    <div>
      <div className="page-title">SMS attendance alerts</div>

      {/* Config */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Alert configuration</div>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="input-label">Threshold (%)</label>
            <input type="number" className="input" style={{ width: 100 }}
              min={0} max={100} value={threshold}
              onChange={e => setThreshold(Number(e.target.value))} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="input-label">From date</label>
            <input type="date" className="input" style={{ width: 150 }}
              value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="input-label">To date</label>
            <input type="date" className="input" style={{ width: 150 }}
              value={dateTo} onChange={e => setDateTo(e.target.value)} />
          </div>
          <button className="btn btn-ghost" onClick={loadRates}>Refresh</button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid-3" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Total students</div>
          <div className="stat-value">{rates.length}</div>
        </div>
        <div className="card">
          <div className="card-title">Below {threshold}%</div>
          <div className="stat-value warn">{below.length}</div>
          <div className="stat-label">will receive SMS</div>
        </div>
        <div className="card">
          <div className="card-title">No phone number</div>
          <div className="stat-value danger">{noPhone.length}</div>
          <div className="stat-label">will be skipped</div>
        </div>
      </div>

      {/* Twilio setup notice */}
      <div style={{
        background: "rgba(77,166,255,0.07)", border: "1px solid rgba(77,166,255,0.2)",
        borderRadius: "var(--radius)", padding: "12px 16px", marginBottom: 16,
        fontSize: 12, color: "var(--text1)", lineHeight: 1.7,
      }}>
        <strong style={{ color: "var(--blue)" }}>Twilio setup required to send real SMS.</strong>{" "}
        Set these environment variables before starting the backend:
        <br />
        <code style={{ fontFamily: "var(--font-mono)", color: "var(--accent)" }}>
          set TWILIO_SID=ACxxxx &nbsp; set TWILIO_TOKEN=xxxx &nbsp; set TWILIO_FROM=+1xxxxxxxxxx
        </code>
        <br />
        Then run <code style={{ fontFamily: "var(--font-mono)", color: "var(--accent)" }}>pip install twilio</code>.
        Use <strong>Preview</strong> to test without sending.
      </div>

      {error  && <div className="error-msg">{error}</div>}

      {result && (
        <div className={result.dry ? "success-msg" : "success-msg"} style={{ marginBottom: 16 }}>
          {result.dry ? (
            <>Preview: {result.total} student(s) would receive SMS. {noPhone.length > 0 && `${noPhone.length} skipped (no phone).`}</>
          ) : (
            <>Sent: {result.total_sent} &nbsp;|&nbsp; Failed: {result.failed?.length ?? 0} &nbsp;|&nbsp; Skipped: {result.skipped?.length ?? 0}</>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <button className="btn btn-ghost" disabled={sending || below.length === 0}
          onClick={() => handleSend(true)}>
          Preview ({below.length} students)
        </button>
        <button className="btn btn-primary" disabled={sending || below.length === 0}
          onClick={() => handleSend(false)}>
          {sending ? "Sending…" : `Send SMS to ${below.length} student(s)`}
        </button>
      </div>

      {/* Rates table */}
      <div className="card">
        <div className="card-title">All student attendance rates</div>
        {loading ? <div className="loading">Loading…</div> :
         rates.length === 0 ? <div className="empty-state">No data yet</div> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Name</th><th>Phone</th><th>Present</th><th>Total days</th><th>Rate</th><th>Status</th></tr>
              </thead>
              <tbody>
                {rates.map(r => (
                  <tr key={r.name}>
                    <td className="name">{r.name}</td>
                    <td className="mono">{r.phone || <span style={{ color: "var(--text2)" }}>—</span>}</td>
                    <td className="mono">{r.present}</td>
                    <td className="mono">{r.total_days}</td>
                    <td>
                      <span style={{
                        fontFamily: "var(--font-mono)", fontSize: 13,
                        fontWeight: 500, color: rateColor(r.rate),
                      }}>{r.rate}%</span>
                    </td>
                    <td>
                      {r.rate < threshold
                        ? <span className="badge late">Alert</span>
                        : <span className="badge present">OK</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}