import { useEffect, useState } from "react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

export default function OwnerEscalations() {
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [replyById, setReplyById] = useState({});
  const [actionError, setActionError] = useState("");

  const loadEscalations = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/ai/escalations/owner");
      setItems(res.data ?? []);
    } catch (err) {
      setItems([]);
      setError(err?.response?.data?.detail ?? "Failed to load escalations");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadEscalations();
  }, []);

  const sendReply = async (interactionId) => {
    setActionError("");
    const reply = (replyById[interactionId] ?? "").trim();
    if (!reply) {
      setActionError("Write a reply first.");
      return;
    }

    try {
      await api.post(`/ai/escalations/${interactionId}/reply`, { reply });
      setItems((prev) => prev.filter((item) => item.id !== interactionId));
      setReplyById((prev) => {
        const next = { ...prev };
        delete next[interactionId];
        return next;
      });
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? "Failed to send reply");
    }
  };

  return (
    <div className="container">
      <div className="section-header">
        <div>
          <h1 className="page-title">AI Escalations</h1>
          <p className="page-subtitle">Reply to customers when the AI escalates medical-risk questions.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={loadEscalations} disabled={isLoading}>
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{error}</div> : null}
      {actionError ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{actionError}</div> : null}

      {items.length === 0 && !isLoading ? (
        <div className="card reveal" style={{ marginTop: "1rem" }}>
          <p className="help">No escalations pending.</p>
        </div>
      ) : (
        <div className="stack" style={{ marginTop: "1rem" }}>
          {items.map((item) => (
            <section key={item.id} className="card reveal">
              <header className="card-header">
                <div>
                  <h2 className="card-title">Escalation #{item.id}</h2>
                  <p className="card-description">Received {formatDate(item.created_at)}</p>
                </div>
                <span className="badge">Chat: {item.customer_id}</span>
              </header>

              <div className="grid" style={{ gap: "0.6rem" }}>
                <div>
                  <p className="label">Customer</p>
                  <p className="help" style={{ whiteSpace: "pre-wrap" }}>{item.customer_query}</p>
                </div>

                <div>
                  <p className="label">AI response</p>
                  <p className="help" style={{ whiteSpace: "pre-wrap" }}>{item.ai_response}</p>
                </div>

                <div className="form-row">
                  <label className="label" htmlFor={`reply-${item.id}`}>
                    Your reply
                  </label>
                  <textarea
                    id={`reply-${item.id}`}
                    className="textarea"
                    rows={3}
                    value={replyById[item.id] ?? ""}
                    onChange={(e) => setReplyById((prev) => ({ ...prev, [item.id]: e.target.value }))}
                    placeholder="Write guidance for the customer..."
                  />
                </div>

                <div className="actions" style={{ justifyContent: "flex-start" }}>
                  <button type="button" className="btn btn-primary" onClick={() => sendReply(item.id)}>
                    Send reply
                  </button>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

