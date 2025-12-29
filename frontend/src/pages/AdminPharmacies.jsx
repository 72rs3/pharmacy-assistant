import { useEffect, useState } from "react";
import api from "../api/axios";

export default function AdminPharmacies() {
  const [pharmacies, setPharmacies] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setIsLoading(true);
    setError("");
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
    try {
      await api.post(`/pharmacies/${pharmacyId}/approve`);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to approve pharmacy");
    }
  };

  return (
    <div className="container">
      <div className="section-header">
        <div>
          <h1 className="page-title">Admin: pharmacies</h1>
          <p className="page-subtitle">Approve pharmacy tenants to make them visible to customers.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={load} disabled={isLoading}>
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{error}</div> : null}

      <div className="stack" style={{ marginTop: "1rem" }}>
        {pharmacies.map((pharmacy) => {
          const approved = pharmacy.status === "APPROVED" && pharmacy.is_active;
          return (
            <section key={pharmacy.id} className="card reveal">
              <header className="card-header">
                <div>
                  <h2 className="card-title">{pharmacy.name}</h2>
                  <p className="card-description">
                    {pharmacy.domain ? `Domain: ${pharmacy.domain}` : "No domain configured"} ·{" "}
                    {approved ? "Approved" : "Pending"}
                  </p>
                </div>
                {approved ? (
                  <span className="badge badge-success">Approved</span>
                ) : (
                  <button type="button" className="btn btn-primary" onClick={() => approve(pharmacy.id)}>
                    Approve
                  </button>
                )}
              </header>
            </section>
          );
        })}
      </div>
    </div>
  );
}

