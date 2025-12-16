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
      const response = await api.get("/pharmacies/admin", {
        params: { status: "PENDING" },
      });
      setPharmacies(response.data);
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
    try {
      await api.post(`/pharmacies/${pharmacyId}/approve`);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Approval failed");
    }
  };

  if (isLoading && pharmacies.length === 0) {
    return <div style={{ padding: "1rem" }}>Loading...</div>;
  }

  return (
    <div style={{ padding: "1rem" }}>
      <h2>Pending Pharmacies</h2>
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}

      {pharmacies.length === 0 ? (
        <p>No pending pharmacies.</p>
      ) : (
        <ul>
          {pharmacies.map((pharmacy) => (
            <li key={pharmacy.id} style={{ marginBottom: "0.75rem" }}>
              <div>
                <strong>{pharmacy.name}</strong> (id: {pharmacy.id}) -{" "}
                {pharmacy.status} / {pharmacy.is_active ? "active" : "inactive"}
              </div>
              <button type="button" onClick={() => approve(pharmacy.id)}>
                Approve
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
