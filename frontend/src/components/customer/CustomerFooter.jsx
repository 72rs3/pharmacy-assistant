import { Link } from "react-router-dom";
import { Heart, Mail, MapPin, Phone, ShieldCheck } from "lucide-react";
import { useCustomerUi } from "../../utils/customer-ui";

export default function CustomerFooter({
  brandName = "Sunr",
  logoUrl = "",
  address = "123 Health Avenue, Suite 101, Wellness City, WC 12345",
  phone = "(555) 123-4567",
  email = "info@sunrpharmacy.com",
}) {
  const normalizedBrand = brandName?.trim() || "Sunr";
  const primaryBrand = /pharmacy/i.test(normalizedBrand)
    ? normalizedBrand.replace(/pharmacy/i, "").trim() || normalizedBrand
    : normalizedBrand;
  const { openChat } = useCustomerUi();
  const year = new Date().getFullYear();
  const phoneHref = `tel:${String(phone).replace(/[^\d+]/g, "")}`;
  const hasLogo = Boolean(logoUrl);
  return (
    <footer className="bg-gray-900 text-gray-300 mt-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid md:grid-cols-4 gap-8">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center overflow-hidden bg-white border border-gray-800">
                {hasLogo ? (
                  <img src={logoUrl} alt={`${primaryBrand} logo`} className="w-full h-full object-contain" />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-primary-600)] flex items-center justify-center">
                    <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
                      <path d="M16 8V24M8 16H24" stroke="white" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                  </div>
                )}
              </div>
              <div>
                <div className="text-white">{primaryBrand}</div>
                <div className="text-[var(--brand-primary)] text-sm">Pharmacy</div>
              </div>
            </div>
            <p className="text-sm">Your trusted partner for wellness and healthcare solutions.</p>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <ShieldCheck className="w-4 h-4" />
              <span>Private by design - Always confirm with a pharmacist</span>
            </div>
          </div>

          <div>
            <h3 className="text-white mb-4">Quick Links</h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/" className="hover:text-white transition-colors">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/shop" className="hover:text-white transition-colors">
                  Shop
                </Link>
              </li>
              <li>
                <Link to="/contact" className="hover:text-white transition-colors">
                  Contact
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="text-white mb-4">Services</h3>
            <ul className="space-y-2 text-sm">
              <li>
                <button type="button" onClick={openChat} className="hover:text-white transition-colors">
                  Prescription questions
                </button>
              </li>
              <li>
                <button type="button" onClick={openChat} className="hover:text-white transition-colors">
                  Health consultations
                </button>
              </li>
              <li>
                <button type="button" onClick={openChat} className="hover:text-white transition-colors">
                  Delivery & pickup
                </button>
              </li>
              <li>
                <button type="button" onClick={openChat} className="hover:text-white transition-colors">
                  Vaccinations & appointments
                </button>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="text-white mb-4">Contact Us</h3>
            <ul className="space-y-3 text-sm">
              <li className="flex items-start gap-2">
                <MapPin className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{address}</span>
              </li>
              <li className="flex items-center gap-2">
                <Phone className="w-4 h-4 flex-shrink-0" />
                <a href={phoneHref} className="hover:text-white transition-colors">
                  {phone}
                </a>
              </li>
              <li className="flex items-center gap-2">
                <Mail className="w-4 h-4 flex-shrink-0" />
                <a href={`mailto:${email}`} className="hover:text-white transition-colors">
                  {email}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="border-t border-gray-800 mt-8 pt-8 flex flex-col md:flex-row justify-between items-center gap-4 text-sm">
          <p>(c) {year} {primaryBrand} Pharmacy. All rights reserved.</p>
          <div className="flex items-center gap-1">
            <span>Made with</span>
            <Heart className="w-4 h-4 text-red-500 fill-red-500" />
            <span>for your health</span>
          </div>
          <div className="flex gap-6">
            <button type="button" onClick={openChat} className="hover:text-white transition-colors">
              Medical disclaimer
            </button>
            <a href="#" className="hover:text-white transition-colors">
              Privacy Policy
            </a>
            <a href="#" className="hover:text-white transition-colors">
              Terms of Service
            </a>
          </div>
        </div>

        <p className="mt-6 text-xs text-gray-400 leading-relaxed">
          Information on this site is for general education and is not medical advice. For emergencies, call local
          emergency services immediately.
        </p>
      </div>
    </footer>
  );
}
