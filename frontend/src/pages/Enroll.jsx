import { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function Enroll() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("student");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadUsers = () => {
    setLoading(true);
    fetch(`${API}/users?active_only=false`)
      .then((r) => r.json())
      .then((data) => { setUsers(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { loadUsers(); }, []);

  const handleCreate = async () => {
    if (!name.trim()) { setError("Name is required."); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      const res = await fetch(`${API}/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), email: email.trim() || null, role }),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || "Failed to create user.");
      } else {
        setSuccess(`'${name.trim()}' enrolled. Run the face engine to add their photo.`);
        setName(""); setEmail(""); setRole("student");
        loadUsers();
      }
    } catch {
      setError("Cannot reach the API. Is the backend running?");
    }
    setSaving(false);
  };

  const handleDeactivate = async (userName) => {
    if (!confirm(`Deactivate '${userName}'?`)) return;
    await fetch(`${API}/users/${encodeURIComponent(userName)}`, { method: "DELETE" });
    loadUsers();
  };

  return (
    <div>
      <div className="page-title">Manage enrolled users</div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <div className="card-title">Register new user</div>

          {error   && <div className="error-msg">{error}</div>}
          {success && <div className="success-msg">{success}</div>}

          <div className="field">
            <label className="input-label">Full name *</label>
            <input
              className="input" placeholder="e.g. Priya Sharma"
              value={name} onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="input-label">Email (optional)</label>
            <input
              className="input" type="email" placeholder="priya@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="input-label">Role</label>
            <select
              className="input"
              value={role} onChange={(e) => setRole(e.target.value)}
            >
              <option value="student">Student</option>
              <option value="staff">Staff</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <button
            className="btn btn-primary" style={{ width: "100%" }}
            onClick={handleCreate} disabled={saving}
          >
            {saving ? "Saving…" : "Add to system"}
          </button>

          <div className="divider" />

          <div className="card-title">Enroll face from terminal</div>
          <div style={{ background: "var(--bg0)", borderRadius: 4, padding: "12px 14px" }}>
            <code style={{
              fontFamily: "var(--font-mono)", fontSize: 12,
              color: "var(--accent)", display: "block", lineHeight: 1.9,
            }}>
              # From a photo:<br />
              python face_engine.py enroll --name "Priya Sharma" --image priya.jpg<br />
              <br />
              # Or from webcam:<br />
              python face_engine.py enroll --name "Priya Sharma"<br />
              <br />
              # Start recognition:<br />
              python face_engine.py recognize
            </code>
          </div>
        </div>

        <div className="card">
          <div className="card-title">
            Enrolled users ({users.filter((u) => u.is_active).length} active)
          </div>
          {loading ? (
            <div className="loading">Loading…</div>
          ) : users.length === 0 ? (
            <div className="empty-state">No users enrolled yet</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.45 }}>
                      <td className="name">{u.name}</td>
                      <td><span className={`badge ${u.role}`}>{u.role}</span></td>
                      <td>
                        {u.is_active
                          ? <span className="badge present">Active</span>
                          : <span className="badge absent">Inactive</span>
                        }
                      </td>
                      <td>
                        {u.is_active && (
                          <button
                            className="btn btn-danger"
                            style={{ padding: "4px 10px", fontSize: 11 }}
                            onClick={() => handleDeactivate(u.name)}
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}