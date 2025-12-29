import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import api from "../api/axios";
import { isPortalHost } from "../utils/tenant";

export default function Register() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pharmacyName, setPharmacyName] = useState("");
  const [pharmacyDomain, setPharmacyDomain] = useState("");
  const [isOwner, setIsOwner] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();

  if (!isPortalHost()) {
    return <Navigate to="/" replace />;
  }

  const handleRegister = async (event) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const endpoint = isOwner ? "/auth/register-owner" : "/auth/register";
      await api.post(endpoint, {
        email,
        password,
        full_name: fullName,
        pharmacy_name: isOwner ? pharmacyName : null,
        pharmacy_domain: isOwner ? pharmacyDomain || null : null,
      });
      navigate("/portal/login");
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Registration failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container">
      <div className="narrow">
        <h1 className="page-title">Create an account</h1>
        <p className="page-subtitle">
          Register as an owner to create a pharmacy tenant. Admin approval is required before customers can see it.
        </p>

        <div className="card" style={{ marginTop: "1.25rem" }}>
          <form className="form" onSubmit={handleRegister}>
            {error ? <div className="alert alert-danger">{error}</div> : null}

            <label className="inline" style={{ justifyContent: "space-between" }}>
              <span className="label">Register as pharmacy owner</span>
              <input type="checkbox" checked={isOwner} onChange={(event) => setIsOwner(event.target.checked)} />
            </label>

            <div className="form-row">
              <label className="label" htmlFor="fullName">
                Full name
              </label>
              <input
                id="fullName"
                className="input"
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                required
                autoComplete="name"
              />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                className="input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                autoComplete="new-password"
              />
            </div>

            {isOwner ? (
              <>
                <div className="form-row">
                  <label className="label" htmlFor="pharmacyName">
                    Pharmacy name
                  </label>
                  <input
                    id="pharmacyName"
                    className="input"
                    type="text"
                    value={pharmacyName}
                    onChange={(event) => setPharmacyName(event.target.value)}
                    required
                  />
                </div>

                <div className="form-row">
                  <label className="label" htmlFor="pharmacyDomain">
                    Pharmacy domain
                  </label>
                  <input
                    id="pharmacyDomain"
                    className="input"
                    type="text"
                    placeholder="e.g., sunrise.localhost"
                    value={pharmacyDomain}
                    onChange={(event) => setPharmacyDomain(event.target.value)}
                    required
                  />
                  <div className="help">
                    Recommended for local testing: use a <code>*.localhost</code> domain (example:{" "}
                    <code>sunrise.localhost</code>).
                  </div>
                </div>
              </>
            ) : null}

            <div className="actions">
              <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Creating..." : "Register"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

