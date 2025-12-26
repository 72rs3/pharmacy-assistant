import { useEffect, useState } from "react";
import api from "../api/axios";
import { RefreshCw } from "lucide-react";

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
  const [isSendingId, setIsSendingId] = useState(null);

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

    setIsSendingId(interactionId);
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
    } finally {
      setIsSendingId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">AI Escalations</h1>
            <p className="text-sm text-slate-500 mt-1">Reply to customers when the AI escalates medical-risk questions.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              onClick={loadEscalations}
              disabled={isLoading}
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>

        <div className="p-6 bg-slate-50/60 space-y-4">
          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm" role="alert">
              {error}
            </div>
          ) : null}
          {actionError ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm" role="alert">
              {actionError}
            </div>
          ) : null}

          {items.length === 0 && !isLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
              No escalations pending.
            </div>
          ) : (
            <div className="space-y-4">
              {items.map((item) => (
                <section key={item.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-5 border-b border-slate-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="text-xl font-semibold text-slate-900">Escalation #{item.id}</h2>
                      <p className="text-sm text-slate-500 mt-1">Received {formatDate(item.created_at)}</p>
                    </div>
                    <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-700">
                      Chat: {item.customer_id ?? "—"}
                    </span>
                  </div>

                  <div className="px-6 py-5 space-y-4">
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-2xl border border-slate-200 bg-white p-4">
                        <p className="text-xs font-semibold text-slate-700">Customer</p>
                        <p className="text-sm text-slate-700 mt-2 whitespace-pre-wrap">{item.customer_query ?? ""}</p>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white p-4">
                        <p className="text-xs font-semibold text-slate-700">AI response</p>
                        <p className="text-sm text-slate-700 mt-2 whitespace-pre-wrap">{item.ai_response ?? ""}</p>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor={`reply-${item.id}`}>
                        Your reply
                      </label>
                      <textarea
                        id={`reply-${item.id}`}
                        rows={4}
                        value={replyById[item.id] ?? ""}
                        onChange={(e) => setReplyById((prev) => ({ ...prev, [item.id]: e.target.value }))}
                        placeholder="Write guidance for the customer..."
                        className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                      />
                      <p className="text-xs text-slate-500 mt-2">
                        Keep it clear and actionable. If urgent or high-risk, advise the customer to seek medical help.
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => sendReply(item.id)}
                        disabled={isSendingId === item.id}
                        className="px-5 py-2.5 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                      >
                        {isSendingId === item.id ? "Sending..." : "Send reply"}
                      </button>
                    </div>
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
