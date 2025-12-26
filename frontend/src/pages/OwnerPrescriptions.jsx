import { useEffect, useState } from "react";
import api from "../api/axios";
import PageHeader from "../components/ui/PageHeader";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusTone = (status) => {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "APPROVED") return "status-pill status-pill--success";
  if (normalized === "REJECTED") return "status-pill status-pill--danger";
  return "status-pill";
};

export default function OwnerPrescriptions() {
  const [prescriptions, setPrescriptions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");

  const loadPrescriptions = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/prescriptions/owner");
      setPrescriptions(res.data ?? []);
    } catch (err) {
      setPrescriptions([]);
      setError(err?.response?.data?.detail ?? "Failed to load prescriptions");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPrescriptions();
  }, []);

  const review = async (id, status) => {
    setActionError("");
    try {
      const res = await api.post(`/prescriptions/${id}/review`, { status });
      setPrescriptions((prev) => prev.map((item) => (item.id === id ? res.data : item)));
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? "Failed to update prescription");
    }
  };

  return (
    <div className="container">
      <PageHeader
        title="Prescriptions"
        subtitle="Review uploaded prescriptions and approve or reject them."
        actions={
          <button type="button" className="btn btn-ghost" onClick={loadPrescriptions} disabled={isLoading}>
            {isLoading ? "Refreshing..." : "Refresh"}
          </button>
        }
      />

      {error ? (
        <div className="alert alert-danger mt-4" role="alert">
          {error}
        </div>
      ) : null}
      {actionError ? (
        <div className="alert alert-danger mt-2" role="alert">
          {actionError}
        </div>
      ) : null}

      {prescriptions.length === 0 && !isLoading ? (
        <div className="card reveal mt-4">
          <p className="help">No prescriptions uploaded yet.</p>
        </div>
      ) : (
        <div className="stack mt-4">
          {prescriptions.map((item) => (
            <section key={item.id} className="card reveal">
              <header className="card-header">
                <div>
                  <h2 className="card-title">Prescription #{item.id}</h2>
                  <p className="card-description">Order #{item.order_id} • {formatDate(item.upload_date)}</p>
                </div>
                <span className={statusTone(item.status)}>{item.status}</span>
              </header>

              <div className="grid" style={{ gap: "0.6rem" }}>
                <div className="inline wrap">
                  <span className="badge">File: {item.original_filename ?? "Upload"}</span>
                  <span className="badge">Type: {item.content_type ?? "unknown"}</span>
                </div>

                <div className="actions justify-start">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => review(item.id, "APPROVED")}
                    disabled={item.status === "APPROVED"}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => review(item.id, "REJECTED")}
                    disabled={item.status === "REJECTED"}
                  >
                    Reject
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

