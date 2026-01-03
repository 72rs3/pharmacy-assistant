import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusBadge = (status) => {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized === "NEW") return "bg-blue-50 border-blue-200 text-blue-700";
  if (normalized === "OPEN") return "bg-amber-50 border-amber-200 text-amber-700";
  if (normalized === "CLOSED") return "bg-slate-50 border-slate-200 text-slate-700";
  return "bg-slate-50 border-slate-200 text-slate-700";
};

export default function OwnerInbox() {
  const [statusFilter, setStatusFilter] = useState("NEW");
  const [messages, setMessages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [replyText, setReplyText] = useState("");
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingMessage, setIsLoadingMessage] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");

  const selectedSummary = useMemo(
    () => messages.find((msg) => msg.id === selectedId) ?? null,
    [messages, selectedId]
  );

  const loadList = async ({ silent = false } = {}) => {
    if (!silent) setIsLoadingList(true);
    if (!silent) setError("");
    try {
      const res = await api.get("/contact/owner/messages", {
        params: { status_filter: statusFilter },
      });
      const items = Array.isArray(res.data) ? res.data : [];
      setMessages(items);
      if (!silent) {
        if (!selectedId && items.length) setSelectedId(items[0].id);
      } else if (selectedId && !items.some((m) => m.id === selectedId)) {
        setSelectedId(null);
        setSelectedMessage(null);
      }
    } catch (err) {
      if (!silent) setError(err?.response?.data?.detail ?? "Failed to load inbox");
    } finally {
      if (!silent) setIsLoadingList(false);
    }
  };

  const loadMessage = async (id, { silent = false } = {}) => {
    if (!id) return;
    if (!silent) setIsLoadingMessage(true);
    if (!silent) setError("");
    try {
      const res = await api.get(`/contact/owner/messages/${id}`);
      setSelectedMessage(res.data ?? null);
    } catch (err) {
      if (!silent) setError(err?.response?.data?.detail ?? "Failed to load message");
    } finally {
      if (!silent) setIsLoadingMessage(false);
    }
  };

  useEffect(() => {
    setSelectedId(null);
    setSelectedMessage(null);
    loadList();
  }, [statusFilter]);

  useEffect(() => {
    if (selectedId) loadMessage(selectedId);
  }, [selectedId]);

  useEffect(() => {
    const handle = setInterval(() => {
      loadList({ silent: true });
      if (selectedId) loadMessage(selectedId, { silent: true });
    }, 5000);
    return () => clearInterval(handle);
  }, [selectedId, statusFilter]);

  const sendReply = async () => {
    if (!selectedId) return;
    const trimmed = replyText.trim();
    if (!trimmed) return;
    setIsSending(true);
    setError("");
    try {
      await api.post(`/contact/owner/messages/${selectedId}/reply`, { reply_text: trimmed });
      setReplyText("");
      await loadMessage(selectedId);
      await loadList({ silent: true });
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Failed to send reply");
    } finally {
      setIsSending(false);
    }
  };

  const setStatus = async (nextStatus) => {
    if (!selectedId) return;
    setError("");
    try {
      await api.post(`/contact/owner/messages/${selectedId}/status`, { status: nextStatus });
      await loadMessage(selectedId);
      await loadList({ silent: true });
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Failed to update status");
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Inbox</h1>
            <p className="text-sm text-slate-500 mt-1">Customer contact messages.</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="px-3 py-2 rounded-xl border border-slate-200 text-sm"
            >
              <option value="NEW">New</option>
              <option value="OPEN">Open</option>
              <option value="CLOSED">Closed</option>
              <option value="ALL">All</option>
            </select>
            <button
              type="button"
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              onClick={() => loadList()}
              disabled={isLoadingList}
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>

        {error ? (
          <div className="m-6 rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{error}</div>
        ) : null}

        <div className="grid lg:grid-cols-[320px_1fr] min-h-[520px]">
          <aside className="border-b lg:border-b-0 lg:border-r border-slate-200 bg-slate-50/60">
            {messages.length === 0 && !isLoadingList ? (
              <div className="p-6 text-sm text-slate-600">No messages.</div>
            ) : (
              <div className="divide-y divide-slate-200">
                {messages.map((msg) => (
                  <button
                    key={msg.id}
                    type="button"
                    onClick={() => setSelectedId(msg.id)}
                    className={`w-full text-left px-4 py-4 transition-colors ${
                      selectedId === msg.id ? "bg-white" : "hover:bg-white/80"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-slate-900 truncate">{msg.subject}</div>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] ${statusBadge(msg.status)}`}>
                        {msg.status}
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 mt-1 truncate">{msg.name} • {msg.email}</div>
                    <div className="text-[11px] text-slate-400 mt-1">Received {formatDate(msg.created_at)}</div>
                  </button>
                ))}
              </div>
            )}
          </aside>

          <section className="flex flex-col">
            <div className="flex-1 p-6 space-y-4 bg-white">
              {!selectedId ? (
                <div className="text-sm text-slate-500">Select a message to view it.</div>
              ) : isLoadingMessage ? (
                <div className="text-sm text-slate-500">Loading message...</div>
              ) : !selectedMessage ? (
                <div className="text-sm text-slate-500">No message loaded.</div>
              ) : (
                <>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-slate-900">{selectedMessage.subject}</div>
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusBadge(selectedMessage.status)}`}>
                        {selectedMessage.status}
                      </span>
                    </div>
                    <div className="mt-2 text-sm text-slate-700">
                      <div className="text-xs text-slate-500">From</div>
                      <div className="font-medium">{selectedMessage.name}</div>
                      <div className="text-slate-600">{selectedMessage.email}</div>
                      {selectedMessage.phone ? <div className="text-slate-600">{selectedMessage.phone}</div> : null}
                    </div>
                    <div className="mt-3 text-xs text-slate-500">Received {formatDate(selectedMessage.created_at)}</div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="text-xs font-semibold text-slate-700 mb-2">Message</div>
                    <div className="text-sm text-slate-800 whitespace-pre-line">{selectedMessage.message}</div>
                  </div>

                  {selectedMessage.reply_text ? (
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                      <div className="text-xs font-semibold text-emerald-800 mb-2">Reply sent</div>
                      <div className="text-sm text-emerald-900 whitespace-pre-line">{selectedMessage.reply_text}</div>
                      {selectedMessage.replied_at ? (
                        <div className="text-xs text-emerald-700 mt-2">Sent {formatDate(selectedMessage.replied_at)}</div>
                      ) : null}
                    </div>
                  ) : null}
                </>
              )}
            </div>

            {selectedId ? (
              <div className="border-t border-slate-200 p-6 bg-white space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-900">Reply</div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setStatus("OPEN")}
                      className="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-700 hover:bg-slate-50"
                      disabled={!selectedSummary || selectedSummary.status === "OPEN"}
                    >
                      Mark open
                    </button>
                    <button
                      type="button"
                      onClick={() => setStatus("CLOSED")}
                      className="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-700 hover:bg-slate-50"
                    >
                      Close
                    </button>
                  </div>
                </div>
                <textarea
                  value={replyText}
                  onChange={(event) => setReplyText(event.target.value)}
                  rows={4}
                  className="w-full px-4 py-3 border border-slate-200 rounded-2xl text-sm"
                  placeholder="Write a reply to the customer (stored in the inbox for now)."
                />
                <button
                  type="button"
                  onClick={sendReply}
                  disabled={isSending || !replyText.trim()}
                  className="w-full py-3 bg-[var(--brand-primary)] text-white rounded-2xl hover:bg-[var(--brand-primary-600)] disabled:opacity-60"
                >
                  {isSending ? "Sending..." : "Send reply & close"}
                </button>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}
