import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import api from "../api/axios";
import { isPortalHost } from "../utils/tenant";
import { isValidEmail } from "../utils/validation";

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
    if (!isValidEmail(email)) {
      setError("Enter a valid email address.");
      return;
    }
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
    <form className="portal-auth-form" onSubmit={handleRegister}>
      {error ? <div className="portal-auth-error">{error}</div> : null}

      <label className="portal-auth-toggle">
        <span>Register as pharmacy owner</span>
        <input type="checkbox" checked={isOwner} onChange={(event) => setIsOwner(event.target.checked)} />
      </label>

      <div className="portal-auth-field">
        <label className="portal-auth-label" htmlFor="fullName">
          Full name
        </label>
        <input
          id="fullName"
          className="portal-auth-input"
          type="text"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          required
          autoComplete="name"
          placeholder="Name"
        />
      </div>

      <div className="portal-auth-field">
        <label className="portal-auth-label" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          className="portal-auth-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
          placeholder="Email Address"
        />
      </div>

      <div className="portal-auth-field">
        <label className="portal-auth-label" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          className="portal-auth-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          autoComplete="new-password"
          placeholder="Password"
        />
      </div>

      {isOwner ? (
        <>
          <div className="portal-auth-field">
            <label className="portal-auth-label" htmlFor="pharmacyName">
              Pharmacy name
            </label>
            <input
              id="pharmacyName"
              className="portal-auth-input"
              type="text"
              value={pharmacyName}
              onChange={(event) => setPharmacyName(event.target.value)}
              required
              placeholder="Pharmacy Name"
            />
          </div>

          <div className="portal-auth-field">
            <label className="portal-auth-label" htmlFor="pharmacyDomain">
              Pharmacy domain
            </label>
            <input
              id="pharmacyDomain"
              className="portal-auth-input"
              type="text"
              placeholder="e.g., sunrise.localhost"
              value={pharmacyDomain}
              onChange={(event) => setPharmacyDomain(event.target.value)}
              required
            />
            <div className="portal-auth-help">
              Recommended for local testing: use a <code>*.localhost</code> domain (example: <code>sunrise.localhost</code>).
            </div>
          </div>
        </>
      ) : null}

      <button className="portal-auth-button" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Creating..." : "Register"}
      </button>

      <p className="portal-auth-footer">
        Already have an account?{" "}
        <Link className="portal-auth-link" to="/portal/login">
          Login here
        </Link>
        .
      </p>
    </form>
  );
}
