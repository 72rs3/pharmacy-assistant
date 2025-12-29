import { useEffect, useState } from "react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

export default function AdminAILogs() {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const loadLogs = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/ai/admin/logs");
      setLogs(res.data ?? []);
    } catch (err) {
      setLogs([]);
      setError(err?.response?.data?.detail ?? "Failed to load AI logs");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  return (
    <div className="container">
      <div className="section-header">
        <div>
          <h1 className="page-title">AI Logs</h1>
          <p className="page-subtitle">Monitor AI usage and escalations across tenants.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={loadLogs} disabled={isLoading}>
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{error}</div> : null}

      {logs.length === 0 && !isLoading ? (
        <div className="card reveal" style={{ marginTop: "1rem" }}>
          <p className="help">No logs found.</p>
        </div>
      ) : (
        <div className="card reveal" style={{ marginTop: "1rem" }}>
          <ul className="list compact">
            {logs.map((log) => (
              <li key={log.id} className="list-item compact">
                <div>
                  <p className="list-item-title">{log.log_type}</p>
                  <p className="list-item-meta">{formatDate(log.timestamp)} • pharmacy_id {log.pharmacy_id}</p>
                  <p className="help" style={{ whiteSpace: "pre-wrap" }}>{log.details}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

