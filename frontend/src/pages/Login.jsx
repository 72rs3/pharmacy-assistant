import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import { isPortalHost } from "../utils/tenant";

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
    <div className="container">
      <div className="narrow">
        <h1 className="page-title">Portal login</h1>
        <p className="page-subtitle">Sign in as a pharmacy owner or admin.</p>

        <div className="card" style={{ marginTop: "1.25rem" }}>
          <form className="form" onSubmit={handleSubmit}>
            {error ? <div className="alert alert-danger">{error}</div> : null}

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
                autoComplete="current-password"
              />
            </div>

            <div className="actions">
              <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Signing in..." : "Login"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

