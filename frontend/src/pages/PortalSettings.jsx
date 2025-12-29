import { useState } from "react";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

export default function PortalSettings() {
  const { user, isAdmin } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [changeError, setChangeError] = useState("");
  const [changeSuccess, setChangeSuccess] = useState("");

  const [resetEmail, setResetEmail] = useState("");
  const [resetNewPassword, setResetNewPassword] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetSuccess, setResetSuccess] = useState("");

  const submitChangePassword = async (event) => {
    event.preventDefault();
    setChangeError("");
    setChangeSuccess("");
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setChangeSuccess("Password updated.");
    } catch (err) {
      setChangeError(err?.response?.data?.detail ?? "Failed to update password");
    }
  };

  const submitAdminReset = async (event) => {
    event.preventDefault();
    setResetError("");
    setResetSuccess("");
    try {
      await api.post("/auth/admin/reset-password", {
        email: resetEmail,
        new_password: resetNewPassword,
      });
      setResetNewPassword("");
      setResetSuccess("Password reset successfully.");
    } catch (err) {
      setResetError(err?.response?.data?.detail ?? "Failed to reset password");
    }
  };

  return (
    <div className="container">
      <div className="section-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Update your password and manage access.</p>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Change password</h2>
              <p className="card-description">Signed in as {user?.email ?? "user"}.</p>
            </div>
          </header>

          <form className="form" onSubmit={submitChangePassword}>
            {changeError ? <div className="alert alert-danger">{changeError}</div> : null}
            {changeSuccess ? <div className="alert">{changeSuccess}</div> : null}

            <div className="form-row">
              <label className="label" htmlFor="currentPassword">
                Current password
              </label>
              <input
                id="currentPassword"
                className="input"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="newPassword">
                New password
              </label>
              <input
                id="newPassword"
                className="input"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
              />
              <p className="help">Minimum 8 characters.</p>
            </div>

            <button type="submit" className="btn btn-primary">
              Update password
            </button>
          </form>
        </section>

        {isAdmin ? (
          <section className="card reveal">
            <header className="card-header">
              <div>
                <h2 className="card-title">Admin reset password</h2>
                <p className="card-description">Reset an owner/admin password by email.</p>
              </div>
            </header>

            <form className="form" onSubmit={submitAdminReset}>
              {resetError ? <div className="alert alert-danger">{resetError}</div> : null}
              {resetSuccess ? <div className="alert">{resetSuccess}</div> : null}

              <div className="form-row">
                <label className="label" htmlFor="resetEmail">
                  User email
                </label>
                <input
                  id="resetEmail"
                  className="input"
                  type="email"
                  value={resetEmail}
                  onChange={(e) => setResetEmail(e.target.value)}
                  placeholder="owner@example.com"
                  required
                />
              </div>

              <div className="form-row">
                <label className="label" htmlFor="resetPassword">
                  New password
                </label>
                <input
                  id="resetPassword"
                  className="input"
                  type="password"
                  value={resetNewPassword}
                  onChange={(e) => setResetNewPassword(e.target.value)}
                  required
                  minLength={8}
                />
              </div>

              <button type="submit" className="btn btn-primary">
                Reset password
              </button>
            </form>
          </section>
        ) : (
          <section className="card reveal">
            <header className="card-header">
              <div>
                <h2 className="card-title">Need help?</h2>
                <p className="card-description">If you forget your password, ask an admin to reset it.</p>
              </div>
            </header>
            <p className="help">There is no email-based password recovery yet.</p>
          </section>
        )}
      </div>
    </div>
  );
}

