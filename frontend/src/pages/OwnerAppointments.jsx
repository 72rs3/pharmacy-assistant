import { useEffect, useState } from "react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusTone = (status) => {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "CONFIRMED") return "status-pill status-pill--success";
  if (normalized === "CANCELLED") return "status-pill status-pill--danger";
  if (normalized === "COMPLETED") return "status-pill status-pill--info";
  return "status-pill";
};

const STATUS_OPTIONS = ["PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"];

export default function OwnerAppointments() {
  const [appointments, setAppointments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [statusById, setStatusById] = useState({});

  const loadAppointments = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/appointments/owner");
      const data = res.data ?? [];
      setAppointments(data);
      setStatusById(
        data.reduce((acc, appt) => {
          acc[appt.id] = appt.status;
          return acc;
        }, {})
      );
    } catch (err) {
      setAppointments([]);
      setError(err?.response?.data?.detail ?? "Failed to load appointments");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAppointments();
  }, []);

  const updateStatus = async (appointmentId) => {
    setActionError("");
    try {
      const res = await api.post(`/appointments/${appointmentId}/status`, {
        status: statusById[appointmentId],
      });
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? "Failed to update status");
    }
  };

  return (
    <div className="container">
      <div className="section-header">
        <div>
          <h1 className="page-title">Appointments</h1>
          <p className="page-subtitle">Confirm bookings and keep the schedule updated.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={loadAppointments} disabled={isLoading}>
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{error}</div> : null}
      {actionError ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{actionError}</div> : null}

      {appointments.length === 0 && !isLoading ? (
        <div className="card reveal" style={{ marginTop: "1rem" }}>
          <p className="help">No appointments booked yet.</p>
        </div>
      ) : (
        <div className="stack" style={{ marginTop: "1rem" }}>
          {appointments.map((appt) => (
            <section key={appt.id} className="card reveal">
              <header className="card-header">
                <div>
                  <h2 className="card-title">Appointment #{appt.id}</h2>
                  <p className="card-description">
                    {appt.type} • {formatDate(appt.scheduled_time)}
                  </p>
                </div>
                <span className={statusTone(appt.status)}>{appt.status}</span>
              </header>

              <div className="grid" style={{ gap: "0.6rem" }}>
                <div className="inline" style={{ flexWrap: "wrap" }}>
                  <span className="badge">Customer: {appt.customer_name ?? "-"}</span>
                  <span className="badge">Phone: {appt.customer_phone ?? "-"}</span>
                  {appt.vaccine_name ? <span className="badge">Vaccine: {appt.vaccine_name}</span> : null}
                </div>

                <div className="actions" style={{ justifyContent: "flex-start" }}>
                  <label className="inline">
                    <span className="label">Status</span>
                    <select
                      className="input"
                      value={statusById[appt.id] ?? appt.status}
                      onChange={(event) => setStatusById((prev) => ({ ...prev, [appt.id]: event.target.value }))}
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" className="btn btn-primary" onClick={() => updateStatus(appt.id)}>
                    Update
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
