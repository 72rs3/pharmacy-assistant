import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "../api/axios";

const parseBackendDate = (value) => {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === "string") {
    const hasTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(value);
    return new Date(hasTimezone ? value : `${value}Z`);
  }
  return new Date(value);
};

const formatDate = (value) => {
  if (!value) return "";
  const date = parseBackendDate(value);
  if (!date) return "";
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const formatTime = (value) => {
  if (!value) return "";
  const date = parseBackendDate(value);
  if (!date) return "";
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const senderLabel = (senderType) => {
  if (senderType === "USER") return "Customer";
  if (senderType === "PHARMACIST") return "You";
  if (senderType === "SYSTEM") return "System";
  return "AI Assistant";
};

export default function OwnerEscalations() {
  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [messages, setMessages] = useState([]);
  const [replyText, setReplyText] = useState("");
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");

  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) ?? null,
    [selectedSessionId, sessions]
  );

  const loadSessions = async () => {
    setIsLoadingSessions(true);
    setError("");
    try {
      const res = await api.get("/admin/pharmacist/sessions", {
        params: { status_filter: "ESCALATED" },
      });
      const items = res.data ?? [];
      setSessions(items);
      if (!selectedSessionId && items.length) {
        setSelectedSessionId(items[0].session_id);
      }
    } catch (err) {
      setSessions([]);
      setError(err?.response?.data?.detail ?? "Failed to load escalations");
    } finally {
      setIsLoadingSessions(false);
    }
  };

  const loadMessages = async (sessionId) => {
    if (!sessionId) return;
    setIsLoadingMessages(true);
    setActionError("");
    try {
      const res = await api.get(`/admin/pharmacist/sessions/${sessionId}/messages`);
      setMessages(res.data ?? []);
    } catch (err) {
      setMessages([]);
      setActionError(err?.response?.data?.detail ?? "Failed to load chat history");
    } finally {
      setIsLoadingMessages(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    if (!selectedSessionId) return;
    loadMessages(selectedSessionId);
  }, [selectedSessionId]);

  const sendReply = async () => {
    if (!selectedSessionId) return;
    const trimmed = replyText.trim();
    if (!trimmed) {
      setActionError("Write a reply first.");
      return;
    }
    setIsSending(true);
    setActionError("");
    try {
      await api.post(`/admin/pharmacist/sessions/${selectedSessionId}/reply`, { text: trimmed });
      setReplyText("");
      await loadMessages(selectedSessionId);
      await loadSessions();
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? "Failed to send reply");
    } finally {
      setIsSending(false);
    }
  };

  const closeConsultation = async () => {
    if (!selectedSessionId) return;
    setActionError("");
    try {
      await api.post(`/admin/pharmacist/sessions/${selectedSessionId}/close`);
      setReplyText("");
      setMessages([]);
      setSelectedSessionId("");
      await loadSessions();
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? "Failed to close consultation");
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Pharmacist Escalations</h1>
            <p className="text-sm text-slate-500 mt-1">Review escalated AI chats and respond in the same thread.</p>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            onClick={loadSessions}
            disabled={isLoadingSessions}
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        <div className="grid lg:grid-cols-[320px_1fr] min-h-[520px]">
          <aside className="border-b lg:border-b-0 lg:border-r border-slate-200 bg-slate-50/60">
            {error ? (
              <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm m-4" role="alert">
                {error}
              </div>
            ) : null}
            {sessions.length === 0 && !isLoadingSessions ? (
              <div className="p-6 text-sm text-slate-600">No escalations pending.</div>
            ) : (
              <div className="divide-y divide-slate-200">
                {sessions.map((session) => (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.session_id)}
                    className={`w-full text-left px-4 py-4 transition-colors ${
                      selectedSessionId === session.session_id ? "bg-white" : "hover:bg-white/80"
                    }`}
                  >
                    <div className="text-sm font-semibold text-slate-900">Session {session.session_id.slice(0, 8)}</div>
                    <div className="text-xs text-slate-500 mt-1">Customer ID: {session.user_session_id}</div>
                    <div className="text-[11px] text-slate-400 mt-1">Last active {formatDate(session.last_activity_at)}</div>
                  </button>
                ))}
              </div>
            )}
          </aside>

          <section className="flex flex-col">
            <div className="flex-1 p-6 space-y-4 bg-white">
              {actionError ? (
                <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm" role="alert">
                  {actionError}
                </div>
              ) : null}

              {!selectedSessionId ? (
                <div className="text-sm text-slate-500">Select a session to review the conversation.</div>
              ) : isLoadingMessages ? (
                <div className="text-sm text-slate-500">Loading messages...</div>
              ) : messages.length === 0 ? (
                <div className="text-sm text-slate-500">No messages yet.</div>
              ) : (
                <div className="space-y-4">
                  {selectedSession && selectedSession.intake_data ? (
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs font-semibold text-slate-700 mb-2">Patient context</div>
                      <div className="grid sm:grid-cols-2 gap-2 text-sm text-slate-700">
                        <div>
                          <span className="text-xs text-slate-500">Name</span>
                          <div className="font-medium">{selectedSession.intake_data.customer_name ?? "-"}</div>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">Phone</span>
                          <div className="font-medium">{selectedSession.intake_data.customer_phone ?? "-"}</div>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">Age range</span>
                          <div className="font-medium">{selectedSession.intake_data.age_range ?? "-"}</div>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">How long</span>
                          <div className="font-medium">{selectedSession.intake_data.how_long ?? "-"}</div>
                        </div>
                        <div className="sm:col-span-2">
                          <span className="text-xs text-slate-500">Main concern</span>
                          <div className="font-medium whitespace-pre-line">{selectedSession.intake_data.main_concern ?? "-"}</div>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">Current medications</span>
                          <div className="font-medium whitespace-pre-line">{selectedSession.intake_data.current_medications ?? "-"}</div>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">Allergies</span>
                          <div className="font-medium whitespace-pre-line">{selectedSession.intake_data.allergies ?? "-"}</div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {messages.map((message) => {
                    const sender = message.sender_type ?? "SYSTEM";
                    const label = senderLabel(sender);
                    const timeLabel = formatTime(message.created_at);

                    if (sender === "SYSTEM") {
                      return (
                        <div key={message.id} className="flex justify-center">
                          <div className="max-w-[80%] text-center text-xs text-slate-600 bg-slate-50 border border-slate-200 px-3 py-2 rounded-xl">
                            <div className="text-[10px] uppercase tracking-wide text-slate-400">
                              {label}
                              {timeLabel ? ` - ${timeLabel}` : ""}
                            </div>
                            <div className="mt-1 whitespace-pre-line">{message.text}</div>
                          </div>
                        </div>
                      );
                    }

                    const isPharmacist = sender === "PHARMACIST";
                    return (
                      <div key={message.id} className={`flex ${isPharmacist ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[80%] ${isPharmacist ? "items-end" : "items-start"} flex flex-col`}>
                          <div className="text-[11px] text-slate-500 mb-1">
                            {label}
                            {timeLabel ? ` - ${timeLabel}` : ""}
                          </div>
                          <div
                            className={`px-4 py-3 rounded-2xl shadow-sm whitespace-pre-line ${
                              isPharmacist
                                ? "bg-emerald-600 text-white rounded-tr-none"
                                : "bg-slate-100 text-slate-800 rounded-tl-none"
                            }`}
                          >
                            {message.text}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="border-t border-slate-200 bg-white p-4">
              <div className="flex flex-col gap-3">
                <label className="text-xs font-medium text-slate-600">Reply as pharmacist</label>
                <textarea
                  rows={4}
                  value={replyText}
                  onChange={(event) => setReplyText(event.target.value)}
                  placeholder="Write guidance for the customer..."
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                />
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={sendReply}
                    disabled={!selectedSessionId || isSending}
                    className="px-5 py-2.5 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                  >
                    {isSending ? "Sending..." : "Send reply"}
                  </button>
                  <button
                    type="button"
                    onClick={closeConsultation}
                    disabled={!selectedSessionId}
                    className="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    Close consultation
                  </button>
                  <span className="text-xs text-slate-500">Replies are posted in the live customer chat.</span>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
