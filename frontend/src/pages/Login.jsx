import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import { isPortalHost } from "../utils/tenant";
import { isValidEmail } from "../utils/validation";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isPortalHost()) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    if (!isValidEmail(email)) {
      setError("Enter a valid email address.");
      return;
    }
    setIsSubmitting(true);

    try {
      const res = await api.post("/auth/login", { email, password });
      login(res.data?.access_token);
      navigate("/portal", { replace: true });
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form className="portal-auth-form" onSubmit={handleSubmit}>
      {error ? <div className="portal-auth-error">{error}</div> : null}

      <div className="portal-auth-field">
        <label className="portal-auth-label" htmlFor="email">
          Email Address
        </label>
        <input
          id="email"
          className="portal-auth-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
          autoFocus
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
          autoComplete="current-password"
          placeholder="Password"
        />
      </div>

      <button className="portal-auth-button" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Signing in..." : "Login"}
      </button>

      <p className="portal-auth-footer">
        Need an account?{" "}
        <Link className="portal-auth-link" to="/portal/register">
          Create Account
        </Link>
        .
      </p>
    </form>
  );
}
