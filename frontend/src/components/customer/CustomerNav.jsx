import { NavLink } from "react-router-dom";
import { MessageCircle, ShoppingCart } from "lucide-react";
import { useCustomerCart } from "../../context/CustomerCartContext";

export default function CustomerNav({ activeBrand = "Sunr Pharmacy", logoUrl = "", onChatToggle, onCartToggle }) {
  const { totalItems } = useCustomerCart();
  const normalizedBrand = activeBrand?.trim() || "Sunr";
  const hasPharmacy = /pharmacy/i.test(normalizedBrand);
  const primaryBrand = hasPharmacy ? normalizedBrand.replace(/pharmacy/i, "").trim() || normalizedBrand : normalizedBrand;
  const hasLogo = Boolean(logoUrl);

  const getLinkClass = ({ isActive }) =>
    `pb-1 transition-colors ${
      isActive
        ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]"
        : "text-gray-600 hover:text-gray-900"
    }`;

  return (
    <header className="bg-white shadow-sm sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center shadow-md overflow-hidden bg-white border border-gray-100">
              {hasLogo ? (
                <img src={logoUrl} alt={`${primaryBrand} logo`} className="w-full h-full object-contain" />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-primary-600)] flex items-center justify-center">
                  <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                    <path d="M16 8V24M8 16H24" stroke="white" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              )}
            </div>
            <div className="leading-tight">
              <div className="text-xl text-gray-900">{primaryBrand}</div>
              <div className="text-sm text-[var(--brand-accent)]">Pharmacy</div>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-10">
            <NavLink to="/" end className={getLinkClass}>
              Home
            </NavLink>
            <NavLink to="/shop" className={getLinkClass}>
              Shop
            </NavLink>
            <NavLink to="/orders" className={getLinkClass}>
              Track order
            </NavLink>
            <NavLink to="/contact" className={getLinkClass}>
              Contact
            </NavLink>
          </nav>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onCartToggle}
              className="relative flex items-center justify-center w-11 h-11 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
              aria-label="Open cart"
            >
              <ShoppingCart className="w-5 h-5" />
              {totalItems > 0 ? (
                <span className="absolute -top-1.5 -right-1.5 bg-[var(--brand-accent)] text-white text-xs w-5 h-5 rounded-full flex items-center justify-center">
                  {totalItems}
                </span>
              ) : null}
            </button>
            <button
              type="button"
              onClick={onChatToggle}
              className="flex items-center gap-2 px-4 py-2 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 transition-colors shadow-sm"
            >
              <MessageCircle className="w-5 h-5" />
              <span className="hidden sm:inline">AI Assistant</span>
            </button>
          </div>
        </div>

        <div className="md:hidden flex gap-4 pb-3">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Home
          </NavLink>
          <NavLink
            to="/shop"
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Shop
          </NavLink>
          <NavLink
            to="/orders"
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Track
          </NavLink>
          <NavLink
            to="/contact"
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Contact
          </NavLink>
        </div>
      </div>
    </header>
  );
}
