import { useEffect, useState, useRef } from "react";

const API = "http://localhost:8000";

export default function Enroll({ recRunning, setRecRunning }) {
  const [users, setUsers]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [name, setName]         = useState("");
  const [email, setEmail]       = useState("");
  const [phone, setPhone]       = useState("");
  const [role, setRole]         = useState("student");
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState("");
  const [success, setSuccess]   = useState("");
  const [cmdOut, setCmdOut]     = useState("");
  const [cmdRunning, setCmdRunning] = useState(false);
  const logRef = useRef(null);

  const loadUsers = () => {
    setLoading(true);
    fetch(`${API}/users?active_only=false`)
      .then(r => r.json())
      .then(d => { setUsers(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadUsers(); }, []);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [cmdOut]);

  const runCmd = async (body) => {
    setCmdRunning(true);
    setCmdOut(prev => prev + `\n> ${body.command}${body.name ? " --name "+body.name : ""}${body.image_path ? " --image "+body.image_path : ""}\n`);
    try {
      const r = await fetch(`${API}/face/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (d.output) setCmdOut(prev => prev + d.output + "\n");
      if (d.status === "started") {
        setCmdOut(prev => prev + `Recognition started (PID ${d.pid})\n`);
        setRecRunning(true);
      }
      if (d.status === "stopped") {
        setCmdOut(prev => prev + "Recognition stopped.\n");
        setRecRunning(false);
      }
      if (d.status === "already_running") {
        setCmdOut(prev => prev + "Recognition is already running.\n");
      }
    } catch {
      setCmdOut(prev => prev + "ERROR: Cannot reach backend.\n");
    }
    setCmdRunning(false);
  };

  const handleCreate = async () => {
    if (!name.trim()) { setError("Name is required."); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      const res = await fetch(`${API}/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), email: email.trim() || null, phone: phone.trim() || null, role }),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || "Failed to create user.");
      } else {
        setSuccess(`'${name.trim()}' added. Now enroll their face using the controls below.`);
        setName(""); setEmail(""); setPhone(""); setRole("student");
        loadUsers();
      }
    } catch { setError("Cannot reach the API."); }
    setSaving(false);
  };

  const handleDeactivate = async (userName) => {
    if (!confirm(`Deactivate '${userName}'?`)) return;
    await fetch(`${API}/users/${encodeURIComponent(userName)}`, { method: "DELETE" });
    loadUsers();
  };

  return (
    <div>
      <div className="page-title">Enroll &amp; manage</div>

      <div className="grid-2" style={{ marginBottom: 20 }}>
        {/* Register form */}
        <div className="card">
          <div className="card-title">Register new person</div>
          {error   && <div className="error-msg">{error}</div>}
          {success && <div className="success-msg">{success}</div>}

          <div className="field">
            <label className="input-label">Full name *</label>
            <input className="input" placeholder="e.g. Priya Sharma"
              value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="field">
            <label className="input-label">Phone (for SMS alerts)</label>
            <input className="input" placeholder="+919876543210"
              value={phone} onChange={e => setPhone(e.target.value)} />
          </div>
          <div className="field">
            <label className="input-label">Email (optional)</label>
            <input className="input" type="email" placeholder="priya@college.edu"
              value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label className="input-label">Role</label>
            <select className="input" value={role} onChange={e => setRole(e.target.value)}>
              <option value="student">Student</option>
              <option value="staff">Staff</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button className="btn btn-primary" style={{ width: "100%" }}
            onClick={handleCreate} disabled={saving}>
            {saving ? "Saving…" : "Add to system"}
          </button>
        </div>

        {/* Users table */}
        <div className="card">
          <div className="card-title">Enrolled ({users.filter(u => u.is_active).length} active)</div>
          {loading ? <div className="loading">Loading…</div> :
           users.length === 0 ? <div className="empty-state">No users yet</div> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Phone</th><th>Role</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.4 }}>
                      <td className="name">{u.name}</td>
                      <td className="mono">{u.phone || "—"}</td>
                      <td><span className={`badge ${u.role}`}>{u.role}</span></td>
                      <td>{u.is_active
                        ? <span className="badge present">Active</span>
                        : <span className="badge absent">Off</span>}
                      </td>
                      <td>{u.is_active && (
                        <button className="btn btn-danger" style={{ padding: "3px 8px", fontSize: 11 }}
                          onClick={() => handleDeactivate(u.name)}>Remove</button>
                      )}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Face engine controls */}
      <div className="card">
        <div className="card-title">Face engine controls</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>

          {/* Enroll from image */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flex: 1, minWidth: 280 }}>
            <input className="input" placeholder="Name to enroll"
              id="enroll-name" style={{ flex: 1 }} />
            <input className="input" placeholder="Image path (e.g. C:\photos\alice.jpg)"
              id="enroll-img" style={{ flex: 2 }} />
            <button className="btn btn-primary" disabled={cmdRunning}
              onClick={() => {
                const n = document.getElementById("enroll-name").value.trim();
                const img = document.getElementById("enroll-img").value.trim();
                if (!n) { alert("Enter a name"); return; }
                runCmd({ command: "enroll", name: n, image_path: img || null });
              }}>
              Enroll
            </button>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-ghost" disabled={cmdRunning}
              onClick={() => runCmd({ command: "list" })}>
              List faces
            </button>
            {!recRunning ? (
              <button className="btn btn-primary" disabled={cmdRunning}
                onClick={() => runCmd({ command: "recognize", headless: true })}>
                ▶ Start recognition
              </button>
            ) : (
              <button className="btn btn-danger" disabled={cmdRunning}
                onClick={() => runCmd({ command: "stop" })}>
                ■ Stop recognition
              </button>
            )}
          </div>
        </div>

        {/* Terminal output */}
        <div ref={logRef} style={{
          background: "var(--bg0)", borderRadius: 4, padding: "12px 14px",
          fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--accent)",
          minHeight: 120, maxHeight: 260, overflowY: "auto", whiteSpace: "pre-wrap",
          border: "1px solid var(--border)",
        }}>
          {cmdOut || "$ ready — use controls above to run face engine commands"}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: "var(--text2)" }}>
          Note: webcam enroll must be run from terminal. Image-path enroll works from here.
          Recognition runs headless (no popup window) and logs attendance automatically.
        </div>
      </div>
    </div>
  );
}