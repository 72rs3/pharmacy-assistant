import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Copy, RefreshCw, Search } from "lucide-react";
import api from "../api/axios";

export default function AdminPharmacies() {
  const [pharmacies, setPharmacies] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL"); // ALL | PENDING | APPROVED
  const [isApprovingId, setIsApprovingId] = useState(null);
  const [notice, setNotice] = useState("");

  const load = async () => {
    setIsLoading(true);
    setError("");
    setNotice("");
    try {
      const res = await api.get("/pharmacies/admin");
      setPharmacies(res.data ?? []);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to load pharmacies");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const approve = async (pharmacyId) => {
    setError("");
    setNotice("");
    setIsApprovingId(pharmacyId);
    try {
      await api.post(`/pharmacies/${pharmacyId}/approve`);
      await load();
      setNotice("Pharmacy approved.");
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to approve pharmacy");
    } finally {
      setIsApprovingId(null);
    }
  };

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
    const normalized = (value) => String(value ?? "").toUpperCase();
    return (pharmacies ?? []).filter((p) => {
      const approved = normalized(p.status) === "APPROVED" && Boolean(p.is_active);
      const statusOk =
        statusFilter === "ALL" || (statusFilter === "APPROVED" ? approved : statusFilter === "PENDING" ? !approved : true);
      if (!statusOk) return false;
      if (!q) return true;
      const name = (p?.name ?? "").toLowerCase();
      const domain = (p?.domain ?? "").toLowerCase();
      const status = (p?.status ?? "").toLowerCase();
      return name.includes(q) || domain.includes(q) || status.includes(q);
    });
  }, [pharmacies, query, statusFilter]);

  const counts = useMemo(() => {
    const normalized = (value) => String(value ?? "").toUpperCase();
    return (pharmacies ?? []).reduce(
      (acc, p) => {
        const approved = normalized(p.status) === "APPROVED" && Boolean(p.is_active);
        acc.total += 1;
        if (approved) acc.approved += 1;
        else acc.pending += 1;
        return acc;
      },
      { total: 0, approved: 0, pending: 0 }
    );
  }, [pharmacies]);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Pharmacies</h1>
            <p className="text-sm text-slate-500 mt-1">Approve pharmacy tenants to make them visible to customers.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
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
              <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
                Pending: {counts.pending}
              </span>
              <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
                Approved: {counts.approved}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {["ALL", "PENDING", "APPROVED"].map((value) => {
                const active = statusFilter === value;
                const label = value === "ALL" ? "All" : value === "PENDING" ? "Pending" : "Approved";
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setStatusFilter(value)}
                    className={`px-3 py-2 rounded-xl text-sm border ${
                      active ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              className="w-full pl-11 pr-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, domain, or status..."
            />
          </div>

          {filtered.length === 0 && !isLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
              No pharmacies found.
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 overflow-hidden bg-white">
              <div className="max-h-[560px] overflow-auto overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0 z-10">
                    <tr>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Pharmacy</th>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Domain</th>
                      <th className="text-left font-semibold px-4 py-3 text-slate-700">Status</th>
                      <th className="text-right font-semibold px-4 py-3 text-slate-700">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((row) => {
                      const approved = String(row.status ?? "").toUpperCase() === "APPROVED" && Boolean(row.is_active);
                      return (
                        <tr key={row.id} className="border-t border-slate-100">
                          <td className="px-4 py-3">
                            <div className="font-semibold text-slate-900">{row.name ?? `Pharmacy #${row.id}`}</div>
                            <div className="text-xs text-slate-500">ID: {row.id}</div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-xs text-slate-700">{row.domain ?? "—"}</span>
                              {row.domain ? (
                                <button
                                  type="button"
                                  onClick={() => copyText(row.domain)}
                                  className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-700 hover:bg-slate-50"
                                >
                                  <Copy className="w-3.5 h-3.5" />
                                  Copy
                                </button>
                              ) : null}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${
                                approved
                                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                  : "bg-amber-50 text-amber-800 border-amber-200"
                              }`}
                            >
                              {approved ? "Approved" : "Pending"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right">
                            {approved ? (
                              <span className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-sm">
                                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                Approved
                              </span>
                            ) : (
                              <button
                                type="button"
                                onClick={() => approve(row.id)}
                                disabled={isApprovingId === row.id}
                                className="px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                              >
                                {isApprovingId === row.id ? "Approving..." : "Approve"}
                              </button>
                            )}
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
