import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusPill = (status) => {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized === "CONFIRMED") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (normalized === "COMPLETED") return "bg-blue-100 text-blue-800 border-blue-200";
  if (normalized === "CANCELLED") return "bg-red-100 text-red-800 border-red-200";
  return "bg-slate-100 text-slate-800 border-slate-200";
};

const STATUS_OPTIONS = ["PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"];

export default function OwnerAppointments() {
  const [appointments, setAppointments] = useState([]);
  const [statusById, setStatusById] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [isSavingId, setIsSavingId] = useState(null);

  const loadAppointments = async () => {
    setIsLoading(true);
    setError("");
    setActionError("");
    try {
      const res = await api.get("/appointments/owner");
      const data = Array.isArray(res.data) ? res.data : [];
      setAppointments(data);
      setStatusById(
        data.reduce((acc, appt) => {
          acc[appt.id] = appt.status;
          return acc;
        }, {})
      );
    } catch (e) {
      setAppointments([]);
      setError(e?.response?.data?.detail ?? "Failed to load appointments");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAppointments();
  }, []);

  const updateStatus = async (appointmentId) => {
    setActionError("");
    setIsSavingId(appointmentId);
    try {
      const res = await api.post(`/appointments/${appointmentId}/status`, {
        status: statusById[appointmentId],
      });
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Failed to update status");
    } finally {
      setIsSavingId(null);
    }
  };

  const counts = useMemo(() => {
    const normalized = (value) => String(value ?? "").toUpperCase();
    return appointments.reduce(
      (acc, appt) => {
        const s = normalized(appt.status);
        acc.total += 1;
        if (s === "PENDING") acc.pending += 1;
        if (s === "CONFIRMED") acc.confirmed += 1;
        if (s === "COMPLETED") acc.completed += 1;
        if (s === "CANCELLED") acc.cancelled += 1;
        return acc;
      },
      { total: 0, pending: 0, confirmed: 0, completed: 0, cancelled: 0 }
    );
  }, [appointments]);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Appointments</h1>
            <p className="text-sm text-slate-500 mt-1">Confirm bookings and keep the schedule updated.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={loadAppointments}
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
          {error ? <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{error}</div> : null}
          {actionError ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{actionError}</div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Total: {counts.total}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Pending: {counts.pending}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Confirmed: {counts.confirmed}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Completed: {counts.completed}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Cancelled: {counts.cancelled}
            </span>
          </div>

          {appointments.length === 0 && !isLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
              No appointments booked yet.
            </div>
          ) : (
            <div className="space-y-4">
              {appointments.map((appt) => (
                <section key={appt.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-3">
                        <h2 className="text-xl font-semibold text-slate-900">Appointment #{appt.id}</h2>
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusPill(appt.status)}`}>
                          {appt.status}
                        </span>
                      </div>
                      <div className="text-sm text-slate-500 mt-1">
                        {appt.type ?? "Appointment"} • {formatDate(appt.scheduled_time)}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                        Customer: {appt.customer_name ?? "—"}
                      </span>
                      <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                        Phone: {appt.customer_phone ?? "—"}
                      </span>
                      {appt.vaccine_name ? (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                          Vaccine: {appt.vaccine_name}
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className="px-6 py-5 flex flex-col md:flex-row md:items-end gap-3">
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor={`appt-status-${appt.id}`}>
                        Status
                      </label>
                      <select
                        id={`appt-status-${appt.id}`}
                        value={statusById[appt.id] ?? appt.status}
                        onChange={(event) => setStatusById((prev) => ({ ...prev, [appt.id]: event.target.value }))}
                        className="w-full md:w-64 px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                      >
                        {STATUS_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      onClick={() => updateStatus(appt.id)}
                      disabled={isSavingId === appt.id}
                      className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                    >
                      {isSavingId === appt.id ? "Updating..." : "Update"}
                    </button>
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

