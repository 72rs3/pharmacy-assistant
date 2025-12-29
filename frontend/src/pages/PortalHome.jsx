import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { isPortalHost } from "../utils/tenant";

export default function PortalHome() {
  const { token, user, isAdmin } = useAuth();

  if (!isPortalHost()) {
    return <Navigate to="/" replace />;
  }

  const isOwner = Boolean(user?.pharmacy_id) && !Boolean(user?.is_admin);

  return (
    <div className="container">
      <h1 className="page-title">Management portal</h1>
      <p className="page-subtitle">Sign in to manage your pharmacy operations or approve pharmacies as an admin.</p>

      <div className="grid grid-2" style={{ marginTop: "1.25rem" }}>
        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Account</h2>
              <p className="card-description">Access owner tools or approve pharmacies as an admin.</p>
            </div>
          </header>

          {token ? (
            <div className="grid" style={{ gap: "0.75rem" }}>
              <div className="inline" style={{ flexWrap: "wrap" }}>
                <span className="badge">{user?.email ?? "Signed in"}</span>
                {isAdmin ? <span className="badge badge-success">Admin</span> : null}
                {isOwner ? <span className="badge badge-success">Owner</span> : null}
              </div>

              <div className="actions" style={{ justifyContent: "flex-start" }}>
                {isOwner ? (
                  <>
                    <Link className="btn btn-primary" to="/portal/owner/inventory">
                      Inventory
                    </Link>
                    <Link className="btn btn-ghost" to="/portal/owner/orders">
                      Orders
                    </Link>
                    <Link className="btn btn-ghost" to="/portal/owner/prescriptions">
                      Prescriptions
                    </Link>
                    <Link className="btn btn-ghost" to="/portal/owner/appointments">
                      Appointments
                    </Link>
                  </>
                ) : null}
                {isAdmin ? (
                  <Link className="btn btn-primary" to="/portal/admin/pharmacies">
                    Approve pharmacies
                  </Link>
                ) : null}
              </div>

              {!isAdmin && !isOwner ? <p className="help">Your account does not have admin/owner access.</p> : null}
            </div>
          ) : (
            <div className="actions" style={{ justifyContent: "flex-start" }}>
              <Link className="btn btn-primary" to="/portal/login">
                Login
              </Link>
              <Link className="btn btn-ghost" to="/portal/register">
                Register
              </Link>
            </div>
          )}
        </section>

        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Customer website</h2>
              <p className="card-description">
                Customers browse medicines, place COD orders, and book appointments on the pharmacy's public website.
              </p>
            </div>
          </header>

          <p className="help">When you register an owner, you must provide a pharmacy domain for routing.</p>
        </section>
      </div>
    </div>
  );
}

