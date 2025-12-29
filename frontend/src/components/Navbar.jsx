import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTenant } from "../context/TenantContext";
import { isPortalHost } from "../utils/tenant";

export default function Navbar() {
  const { token, user, logout, isAdmin, isOwner } = useAuth();
  const { pharmacy } = useTenant() ?? {};
  const portal = isPortalHost();
  const brandHref = portal ? "/portal" : "/";
  const brandTitle = portal ? "Pharmacy Assistant" : pharmacy?.name ?? "Pharmacy";

  return (
    <header className="app-header">
      <div className="container app-header-inner">
        <Link to={brandHref} className="brand">
          <span className="brand-mark">Rx</span>
          <span>
            {brandTitle}
            <span className="brand-subtitle">{portal ? "Management portal" : "Online storefront"}</span>
          </span>
        </Link>

        {portal ? (
          <nav className="nav-links" aria-label="Primary">
            <NavLink to="/portal" end className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
              Portal
            </NavLink>
            {isOwner ? (
              <>
                <NavLink
                  to="/portal/owner/inventory"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  Inventory
                </NavLink>
                <NavLink
                  to="/portal/owner/orders"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  Orders
                </NavLink>
                <NavLink
                  to="/portal/owner/prescriptions"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  Prescriptions
                </NavLink>
                <NavLink
                  to="/portal/owner/appointments"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  Appointments
                </NavLink>
                <NavLink
                  to="/portal/owner/escalations"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  Escalations
                </NavLink>
              </>
            ) : null}
            {isAdmin ? (
              <>
                <NavLink
                  to="/portal/admin/pharmacies"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  Admin
                </NavLink>
                <NavLink
                  to="/portal/admin/ai-logs"
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  AI Logs
                </NavLink>
              </>
            ) : null}
            {token ? (
              <NavLink
                to="/portal/settings"
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              >
                Settings
              </NavLink>
            ) : null}
          </nav>
        ) : (
          <div />
        )}

        <div className="nav-actions">
          {portal ? (
            token ? (
              <>
                <span className="badge">{user?.email ?? "Signed in"}</span>
                <button type="button" className="btn btn-ghost" onClick={logout}>
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link className="btn btn-link" to="/portal/login">
                  Login
                </Link>
                <Link className="btn btn-primary" to="/portal/register">
                  Register
                </Link>
              </>
            )
          ) : null}
        </div>
      </div>
    </header>
  );
}
