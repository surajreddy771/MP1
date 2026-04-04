import { useEffect, useState } from "react";

const API = "http://localhost:8000";

function fmt(n) { return n ?? "—"; }

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  const today = new Date().toISOString().slice(0, 10);

  // Refresh every 15s
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/stats/overview`).then((r) => r.json()).catch(() => null),
      fetch(`${API}/attendance/summary/${today}`).then((r) => r.json()).catch(() => null),
    ]).then(([s, sum]) => {
      setStats(s);
      setSummary(sum);
      setLoading(false);
    });
  }, [tick]);

  const maxCount = stats?.daily_counts
    ? Math.max(...stats.daily_counts.map((d) => d.count), 1)
    : 1;

  return (
    <div>
      <div className="page-title">
        <span className="live-dot" />
        Live overview — {today}
      </div>

      {loading && <div className="loading">Loading...</div>}

      {!loading && (
        <>
          <div className="grid-3">
            <div className="card">
              <div className="card-title">Present today</div>
              <div className={`stat-value accent`}>{fmt(stats?.today_present)}</div>
              <div className="stat-label">of {fmt(stats?.total_enrolled)} enrolled</div>
            </div>

            <div className="card">
              <div className="card-title">Late arrivals</div>
              <div className={`stat-value ${summary?.late_count > 0 ? "warn" : ""}`}>
                {fmt(summary?.late_count)}
              </div>
              <div className="stat-label">marked late today</div>
            </div>

            <div className="card">
              <div className="card-title">7-day avg rate</div>
              <div className="stat-value">{fmt(stats?.avg_weekly_rate)}%</div>
              <div className="stat-label">attendance rate</div>
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-title">Daily attendance — last 7 days</div>
              {stats?.daily_counts?.length ? (
                stats.daily_counts.map((d) => (
                  <div className="bar-row" key={d.date}>
                    <span className="bar-date">{d.date.slice(5)}</span>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{ width: `${(d.count / maxCount) * 100}%` }}
                      />
                    </div>
                    <span className="bar-count">{d.count}</span>
                  </div>
                ))
              ) : (
                <div className="empty-state">No data yet</div>
              )}
            </div>

            <div className="card">
              <div className="card-title">Absent today ({summary?.absent_names?.length ?? 0})</div>
              {summary?.absent_names?.length ? (
                <div className="table-wrap">
                  <table>
                    <tbody>
                      {summary.absent_names.map((name) => (
                        <tr key={name}>
                          <td className="name">{name}</td>
                          <td><span className="badge absent">Absent</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state" style={{ paddingTop: 24 }}>
                  {stats?.today_present > 0 ? "Everyone is present" : "No data yet"}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}