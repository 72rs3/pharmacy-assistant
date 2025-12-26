import { Link, NavLink, useLocation } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useTenant } from "../context/TenantContext";
import { isPortalHost } from "../utils/tenant";

export default function Navbar() {
  const { token, user, logout, isAdmin, isOwner } = useAuth();
  const { pharmacy } = useTenant() ?? {};
  const portal = isPortalHost();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const brandHref = portal ? "/portal" : "/";
  const brandTitle = portal ? "Pharmacy Assistant" : pharmacy?.name ?? "Pharmacy";

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  const navLinks = useMemo(() => {
    if (!portal) return null;
    return (
      <>
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
              to="/portal/owner/products"
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              Products
            </NavLink>
            <NavLink
              to="/portal/owner/orders"
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              Orders
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
            <NavLink to="/portal/admin/ai-logs" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
              AI Logs
            </NavLink>
          </>
        ) : null}
        {token ? (
          <NavLink to="/portal/settings" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            Settings
          </NavLink>
        ) : null}
      </>
    );
  }, [isAdmin, isOwner, portal, token]);

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
          <>
            <button
              type="button"
              className="nav-toggle"
              aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((prev) => !prev)}
            >
              {menuOpen ? "Close" : "Menu"}
            </button>
            <nav className={`nav-menu${menuOpen ? " open" : ""}`} aria-label="Primary">
              {navLinks}
            </nav>
          </>
        ) : (
          <nav className="nav-links" aria-label="Storefront sections">
            <NavLink className="nav-link" to="/shop">
              Shop
            </NavLink>
            <NavLink className="nav-link" to="/orders">
              Track order
            </NavLink>
            <NavLink className="nav-link" to="/appointments">
              Appointments
            </NavLink>
            <a className="nav-link" href="/shop#assistant">
              AI assistant
            </a>
          </nav>
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
