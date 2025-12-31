import { useEffect, useMemo, useState } from "react";
import { Copy, RefreshCw, Search } from "lucide-react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

export default function AdminAILogs() {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(200);
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [notice, setNotice] = useState("");

  const loadLogs = async () => {
    setIsLoading(true);
    setError("");
    setNotice("");
    try {
      const res = await api.get("/ai/admin/logs", { params: { limit } });
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
  }, [limit]);

  const copyText = async (value) => {
    const text = String(value ?? "");
    if (!text) return;
    setNotice("");
    try {
      await navigator.clipboard.writeText(text);
      setNotice("Copied to clipboard.");
    } catch {
      setNotice("Copy failed. Please copy manually.");
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const normalizedTypeFilter = String(typeFilter ?? "").toUpperCase();
    return (logs ?? []).filter((log) => {
      if (normalizedTypeFilter !== "ALL" && String(log?.log_type ?? "").toUpperCase() !== normalizedTypeFilter) return false;
      if (!q) return true;
      const type = (log?.log_type ?? "").toLowerCase();
      const details = (log?.details ?? "").toLowerCase();
      const pharmacyId = String(log?.pharmacy_id ?? "");
      return type.includes(q) || details.includes(q) || pharmacyId.includes(q);
    });
  }, [logs, query, typeFilter]);

  const counts = useMemo(() => {
    const byType = new Map();
    for (const item of logs ?? []) {
      const t = String(item?.log_type ?? "unknown").toUpperCase();
      byType.set(t, (byType.get(t) ?? 0) + 1);
    }
    const topTypes = Array.from(byType.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);
    return { total: (logs ?? []).length, byType, topTypes };
  }, [logs]);

  const typeOptions = useMemo(() => {
    const set = new Set(["ALL"]);
    for (const item of logs ?? []) set.add(String(item?.log_type ?? "unknown").toUpperCase());
    return Array.from(set).sort((a, b) => (a === "ALL" ? -1 : b === "ALL" ? 1 : a.localeCompare(b)));
  }, [logs]);

  const toggleExpanded = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">AI Logs</h1>
            <p className="text-sm text-slate-500 mt-1">Monitor AI usage and escalations across tenants.</p>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-sm focus:outline-none focus:ring-4 focus:ring-blue-100"
              title="Result limit"
            >
              {[100, 200, 500, 1000].map((n) => (
                <option key={n} value={n}>
                  Limit: {n}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={loadLogs}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
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
          {notice ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm" role="status">
              {notice}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
                Total: {counts.total}
              </span>
              {counts.topTypes.map(([t, n]) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTypeFilter(t)}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs ${
                    typeFilter === t ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                  }`}
                  title="Filter by type"
                >
                  {t.toLowerCase()}: {n}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-sm focus:outline-none focus:ring-4 focus:ring-blue-100"
                title="Type filter"
              >
                {typeOptions.map((t) => (
                  <option key={t} value={t}>
                    {t === "ALL" ? "All types" : t.toLowerCase()}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              className="w-full pl-11 pr-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by type, pharmacy_id, or details..."
            />
          </div>

          {filtered.length === 0 && !isLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">No logs found.</div>
          ) : (
            <div className="rounded-2xl border border-slate-200 overflow-hidden bg-white">
              <div className="max-h-[560px] overflow-auto overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0 z-10">
                    <tr>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Time</th>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Pharmacy</th>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Type</th>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Details</th>
                      <th className="text-right font-semibold px-4 py-3 text-slate-700">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => {
                      const isExpanded = expandedIds.has(row.id);
                      const details = String(row.details ?? "");
                      const short = details.length > 180 ? `${details.slice(0, 180)}…` : details;
                      return (
                        <tr key={row.id} className="border-t border-slate-100 align-top">
                          <td className="px-4 py-3 whitespace-nowrap text-slate-700">{formatDate(row.timestamp)}</td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <button
                              type="button"
                              className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-700 hover:bg-slate-100"
                              title="Filter by pharmacy"
                              onClick={() => setQuery(String(row.pharmacy_id ?? ""))}
                            >
                              #{row.pharmacy_id}
                            </button>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
                              {String(row.log_type ?? "unknown")}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="text-xs text-slate-700 font-mono whitespace-pre-wrap leading-relaxed">
                              {isExpanded ? details : short}
                            </div>
                            {details.length > 180 ? (
                              <button
                                type="button"
                                onClick={() => toggleExpanded(row.id)}
                                className="mt-2 text-xs text-blue-700 hover:underline"
                              >
                                {isExpanded ? "Show less" : "Show more"}
                              </button>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-right whitespace-nowrap">
                            <div className="inline-flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => copyText(details)}
                                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                              >
                                <Copy className="w-4 h-4" />
                                Copy
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
