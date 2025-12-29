import { useEffect, useMemo, useState } from "react";
import api from "../api/axios";

const emptyForm = {
  name: "",
  category: "",
  price: "",
  stock_level: "",
  prescription_required: false,
  dosage: "",
  side_effects: "",
};

export default function OwnerInventory() {
  const [pharmacy, setPharmacy] = useState(null);
  const [medicines, setMedicines] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState(emptyForm);

  const pharmacyStatus = useMemo(() => {
    if (!pharmacy) return null;
    const approved = pharmacy.status === "APPROVED" && pharmacy.is_active;
    return {
      approved,
      label: approved ? "Approved / active" : `${pharmacy.status} / inactive`,
    };
  }, [pharmacy]);

  const load = async () => {
    setIsLoading(true);
    setError("");
    try {
      const [pharmacyRes, medicinesRes] = await Promise.all([
        api.get("/pharmacies/me"),
        api.get("/medicines/owner"),
      ]);
      setPharmacy(pharmacyRes.data);
      setMedicines(medicinesRes.data ?? []);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to load inventory");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    const payload = {
      name: form.name.trim(),
      category: form.category.trim() || null,
      price: Number(form.price),
      stock_level: Number(form.stock_level),
      prescription_required: Boolean(form.prescription_required),
      dosage: form.dosage.trim() || null,
      side_effects: form.side_effects.trim() || null,
    };

    try {
      await api.post("/medicines/owner", payload);
      setForm(emptyForm);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to add medicine");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container">
      <h1 className="page-title">Inventory</h1>
      <p className="page-subtitle">Manage medicines for your pharmacy tenant.</p>

      {error ? (
        <div className="alert alert-danger" style={{ marginTop: "1rem" }}>
          {error}
        </div>
      ) : null}

      <div className="grid grid-2" style={{ marginTop: "1.25rem" }}>
        <div className="grid" style={{ gap: "1rem" }}>
          <section className="card reveal">
            <header className="card-header">
              <div>
                <h2 className="card-title">Pharmacy</h2>
                <p className="card-description">Your tenant status and public availability.</p>
              </div>
              <button type="button" className="btn btn-ghost" onClick={load} disabled={isLoading}>
                {isLoading ? "Refreshing..." : "Refresh"}
              </button>
            </header>

            {pharmacy ? (
              <div className="grid" style={{ gap: "0.75rem" }}>
                <div className="inline" style={{ flexWrap: "wrap" }}>
                  <span className={`badge ${pharmacyStatus?.approved ? "badge-success" : "badge-warning"}`}>
                    {pharmacyStatus?.approved ? "Approved" : "Pending approval"}
                  </span>
                  <span className="badge">ID: {pharmacy.id}</span>
                  {pharmacy.domain ? <span className="badge">{pharmacy.domain}</span> : null}
                </div>

                <div>
                  <div className="label">Name</div>
                  <div>{pharmacy.name}</div>
                </div>

                <div>
                  <div className="label">Status</div>
                  <div>{pharmacyStatus?.label}</div>
                </div>

                {!pharmacyStatus?.approved ? (
                  <div className="alert">Customers cannot see this pharmacy until an admin approves it.</div>
                ) : null}
              </div>
            ) : (
              <p className="help">Loading pharmacy details...</p>
            )}
          </section>

          <section className="card reveal">
            <header className="card-header">
              <div>
                <h2 className="card-title">Add medicine</h2>
                <p className="card-description">Create a new medicine under your pharmacy.</p>
              </div>
            </header>

            <form className="form" onSubmit={submit}>
              <div className="form-row">
                <label className="label" htmlFor="name">
                  Name
                </label>
                <input
                  id="name"
                  className="input"
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                  required
                />
              </div>

              <div className="form-row">
                <label className="label" htmlFor="category">
                  Category (optional)
                </label>
                <input
                  id="category"
                  className="input"
                  type="text"
                  placeholder="e.g., Antibiotic"
                  value={form.category}
                  onChange={(e) => setForm((prev) => ({ ...prev, category: e.target.value }))}
                />
              </div>

              <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div className="form-row">
                  <label className="label" htmlFor="price">
                    Price
                  </label>
                  <input
                    id="price"
                    className="input"
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                    value={form.price}
                    onChange={(e) => setForm((prev) => ({ ...prev, price: e.target.value }))}
                    required
                  />
                </div>

                <div className="form-row">
                  <label className="label" htmlFor="stock">
                    Stock level
                  </label>
                  <input
                    id="stock"
                    className="input"
                    type="number"
                    placeholder="0"
                    value={form.stock_level}
                    onChange={(e) => setForm((prev) => ({ ...prev, stock_level: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <label className="inline" style={{ justifyContent: "space-between" }}>
                <span className="label">Prescription required</span>
                <input
                  type="checkbox"
                  checked={form.prescription_required}
                  onChange={(e) => setForm((prev) => ({ ...prev, prescription_required: e.target.checked }))}
                />
              </label>

              <div className="form-row">
                <label className="label" htmlFor="dosage">
                  Dosage (optional)
                </label>
                <input
                  id="dosage"
                  className="input"
                  type="text"
                  placeholder="e.g., 500mg"
                  value={form.dosage}
                  onChange={(e) => setForm((prev) => ({ ...prev, dosage: e.target.value }))}
                />
              </div>

              <div className="form-row">
                <label className="label" htmlFor="sideEffects">
                  Side effects (optional)
                </label>
                <textarea
                  id="sideEffects"
                  className="textarea"
                  value={form.side_effects}
                  onChange={(e) => setForm((prev) => ({ ...prev, side_effects: e.target.value }))}
                  rows={3}
                />
              </div>

              <div className="actions">
                <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Adding..." : "Add medicine"}
                </button>
              </div>
            </form>
          </section>
        </div>

        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Medicines</h2>
              <p className="card-description">Your pharmacy inventory list.</p>
            </div>
          </header>

          {isLoading && medicines.length === 0 ? <p className="help">Loading...</p> : null}

          {medicines.length === 0 ? (
            <p className="help">No medicines yet.</p>
          ) : (
            <ul className="list">
              {medicines.map((medicine) => (
                <li key={medicine.id} className="list-item">
                  <div>
                    <p className="list-item-title">
                      {medicine.name} <span className="help">$ {medicine.price}</span>
                    </p>
                    <p className="list-item-meta">
                      {medicine.category ? `Category: ${medicine.category} · ` : ""}
                      {medicine.prescription_required ? "Prescription required" : "OTC"}
                      {" · "}
                      Stock: {medicine.stock_level}
                    </p>
                  </div>
                  <span className={`badge ${medicine.stock_level > 0 ? "badge-success" : "badge-danger"}`}>
                    {medicine.stock_level > 0 ? "In stock" : "Out of stock"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

