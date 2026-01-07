import { useCallback, useEffect, useMemo, useState } from "react";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import { RefreshCw } from "lucide-react";
import { isValidE164, isValidEmail } from "../utils/validation";
import PhoneInput from "../components/ui/PhoneInput";

export default function PortalSettings() {
  const { user, isAdmin } = useAuth();
  const isOwner = Boolean(user?.pharmacy_id) && !user?.is_admin;
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [changeError, setChangeError] = useState("");
  const [changeSuccess, setChangeSuccess] = useState("");

  const [pharmacy, setPharmacy] = useState(null);
  const [pharmacyLoading, setPharmacyLoading] = useState(false);
  const [pharmacyError, setPharmacyError] = useState("");
  const [pharmacySuccess, setPharmacySuccess] = useState("");
  const [brandingForm, setBrandingForm] = useState({
    branding_details: "",
    operating_hours: "",
    support_cod: true,
    logo_url: "",
    hero_image_url: "",
    primary_color: "",
    primary_color_600: "",
    accent_color: "",
    font_family: "",
    theme_preset: "classic",
    storefront_layout: "classic",
    contact_email: "",
    contact_phone: "",
    contact_address: "",
  });
  const [initialBranding, setInitialBranding] = useState(null);

  const [resetEmail, setResetEmail] = useState("");
  const [resetNewPassword, setResetNewPassword] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetSuccess, setResetSuccess] = useState("");

  const loadMyPharmacy = useCallback(async () => {
    if (!isOwner) return;
    setPharmacyLoading(true);
    setPharmacyError("");
    try {
      const res = await api.get("/pharmacies/me");
      const data = res.data;
      setPharmacy(data);
      const nextBranding = {
        branding_details: data?.branding_details ?? "",
        operating_hours: data?.operating_hours ?? "",
        support_cod: Boolean(data?.support_cod),
        logo_url: data?.logo_url ?? "",
        hero_image_url: data?.hero_image_url ?? "",
        primary_color: data?.primary_color ?? "",
        primary_color_600: data?.primary_color_600 ?? "",
        accent_color: data?.accent_color ?? "",
        font_family: data?.font_family ?? "",
        theme_preset: data?.theme_preset ?? "classic",
        storefront_layout: data?.storefront_layout ?? "classic",
        contact_email: data?.contact_email ?? "",
        contact_phone: data?.contact_phone ?? "",
        contact_address: data?.contact_address ?? "",
      };
      setBrandingForm(nextBranding);
      setInitialBranding(nextBranding);
    } catch (err) {
      setPharmacy(null);
      setPharmacyError(err?.response?.data?.detail ?? "Failed to load pharmacy settings");
    } finally {
      setPharmacyLoading(false);
    }
  }, [isOwner]);

  useEffect(() => {
    loadMyPharmacy();
  }, [isOwner, loadMyPharmacy]);

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
    if (!isValidEmail(resetEmail)) {
      setResetError("Enter a valid email address.");
      return;
    }
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

  const submitBranding = async (event) => {
    event.preventDefault();
    setPharmacyError("");
    setPharmacySuccess("");
    if (brandingForm.contact_email && !isValidEmail(brandingForm.contact_email)) {
      setPharmacyError("Contact email must be a valid email address.");
      return;
    }
    if (brandingForm.contact_phone && !isValidE164(brandingForm.contact_phone)) {
      setPharmacyError("Contact phone must be E.164 format, e.g. +15551234567.");
      return;
    }
    try {
      const res = await api.patch("/pharmacies/me", {
        ...brandingForm,
      });
      setPharmacy(res.data);
      setInitialBranding(brandingForm);
      setPharmacySuccess("Branding updated.");
    } catch (err) {
      setPharmacyError(err?.response?.data?.detail ?? "Failed to update pharmacy branding");
    }
  };

  const isBrandingDirty = useMemo(() => {
    if (!initialBranding) return false;
    return JSON.stringify(initialBranding) !== JSON.stringify(brandingForm);
  }, [brandingForm, initialBranding]);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-200">
          <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Settings</h1>
          <p className="text-sm text-slate-500 mt-1">Update your password and manage access.</p>
        </div>

        <div className="p-6 bg-slate-50/60">
          <div className="grid gap-6">
            {isOwner ? (
              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-5 border-b border-slate-200 flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="text-lg font-semibold text-slate-900">Pharmacy branding</h2>
                    <p className="text-sm text-slate-500 mt-1">
                      Customize your storefront appearance. Changes apply instantly to your pharmacy domain.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={loadMyPharmacy}
                    disabled={pharmacyLoading}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                    title="Refresh"
                  >
                    <RefreshCw className="w-4 h-4" />
                    Refresh
                  </button>
                </div>

                <div className="px-6 py-6 space-y-6">
                  {pharmacyError ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{pharmacyError}</div>
                  ) : null}
                  {pharmacySuccess ? (
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
                      {pharmacySuccess}
                    </div>
                  ) : null}

                  <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
                    <nav className="space-y-2 text-sm rounded-2xl border border-slate-200 bg-white p-4 lg:sticky lg:top-6">
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Sections</div>
                      <a href="#branding-profile" className="block px-3 py-2 rounded-xl text-slate-600 hover:bg-slate-50">
                        Store profile
                      </a>
                      <a href="#branding-appearance" className="block px-3 py-2 rounded-xl text-slate-600 hover:bg-slate-50">
                        Appearance
                      </a>
                      <a href="#branding-contact" className="block px-3 py-2 rounded-xl text-slate-600 hover:bg-slate-50">
                        Contact
                      </a>
                      <a href="#branding-assets" className="block px-3 py-2 rounded-xl text-slate-600 hover:bg-slate-50">
                        Media
                      </a>
                    </nav>

                    <form id="branding-form" className="space-y-6 pb-24" onSubmit={submitBranding}>
                      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
                        <div className="space-y-6">
                          <section id="branding-profile" className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                            <div>
                              <div className="text-sm font-semibold text-slate-900">Store profile</div>
                              <p className="text-xs text-slate-500 mt-1">Basics that show up in your storefront and AI replies.</p>
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="text-sm text-slate-700">
                                <span className="font-medium">Store name:</span> {pharmacy?.name ?? "Your pharmacy"}
                              </div>
                              {pharmacy?.name ? (
                                <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-700">
                                  ID: {pharmacy?.id}
                                </span>
                              ) : null}
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="brandingDetails">
                                About / description
                              </label>
                              <textarea
                                id="brandingDetails"
                                rows={4}
                                value={brandingForm.branding_details}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, branding_details: e.target.value }))}
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              />
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="operatingHours">
                                Operating hours
                              </label>
                              <div className="text-[11px] text-slate-500 mb-2">
                                Shown to customers and used by the AI assistant for store hour questions.
                              </div>
                              <input
                                id="operatingHours"
                                value={brandingForm.operating_hours}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, operating_hours: e.target.value }))}
                                placeholder="Mon-Fri 9am-7pm, Sat 10am-5pm"
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              />
                            </div>

                            <label className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-700">
                              <span className="text-sm">Cash on delivery enabled</span>
                              <input
                                type="checkbox"
                                checked={brandingForm.support_cod}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, support_cod: e.target.checked }))}
                                className="accent-blue-600"
                              />
                            </label>
                          </section>

                          <section id="branding-appearance" className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                            <div>
                              <div className="text-sm font-semibold text-slate-900">Appearance</div>
                              <p className="text-xs text-slate-500 mt-1">Define colors, typography, and layout defaults.</p>
                            </div>

                            <div className="grid gap-4">
                              <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="primaryColor">
                                  Primary color (hex)
                                </label>
                                <input
                                  id="primaryColor"
                                  value={brandingForm.primary_color}
                                  onChange={(e) => setBrandingForm((prev) => ({ ...prev, primary_color: e.target.value }))}
                                  placeholder="#7CB342"
                                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="primaryColor600">
                                  Primary 600 (hex)
                                </label>
                                <input
                                  id="primaryColor600"
                                  value={brandingForm.primary_color_600}
                                  onChange={(e) => setBrandingForm((prev) => ({ ...prev, primary_color_600: e.target.value }))}
                                  placeholder="#689F38"
                                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                                />
                              </div>
                            </div>

                            <div className="grid gap-4">
                              <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="accentColor">
                                  Accent color (hex)
                                </label>
                                <input
                                  id="accentColor"
                                  value={brandingForm.accent_color}
                                  onChange={(e) => setBrandingForm((prev) => ({ ...prev, accent_color: e.target.value }))}
                                  placeholder="#3B82F6"
                                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="fontFamily">
                                  Font family (CSS)
                                </label>
                                <input
                                  id="fontFamily"
                                  value={brandingForm.font_family}
                                  onChange={(e) => setBrandingForm((prev) => ({ ...prev, font_family: e.target.value }))}
                                  placeholder="system-ui, -apple-system, Segoe UI, sans-serif"
                                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                                />
                              </div>
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="themePreset">
                                Storefront preset
                              </label>
                              <select
                                id="themePreset"
                                value={brandingForm.theme_preset}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, theme_preset: e.target.value }))}
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              >
                                <option value="classic">Classic (clean & familiar)</option>
                                <option value="fresh">Fresh (bright & friendly)</option>
                                <option value="minimal">Minimal (quiet & modern)</option>
                                <option value="glass">Glass (frosted & premium)</option>
                                <option value="neumorph">Neumorph (soft depth)</option>
                              </select>
                              <p className="text-xs text-slate-500 mt-2">Presets set default colors and typography. Custom colors override them.</p>
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="storefrontLayout">
                                Storefront layout
                              </label>
                              <select
                                id="storefrontLayout"
                                value={brandingForm.storefront_layout}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, storefront_layout: e.target.value }))}
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              >
                                <option value="classic">Classic (balanced)</option>
                                <option value="breeze">Breeze (airy)</option>
                                <option value="studio">Studio (editorial)</option>
                                <option value="market">Market (product first)</option>
                              </select>
                              <p className="text-xs text-slate-500 mt-2">Layouts change structure and section order for your storefront.</p>
                            </div>
                          </section>

                          <section id="branding-contact" className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                            <div>
                              <div className="text-sm font-semibold text-slate-900">Contact</div>
                              <p className="text-xs text-slate-500 mt-1">Displayed on the store and used for support outreach.</p>
                            </div>

                              <div className="space-y-4">
                              <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="contactEmail">
                                  Contact email
                                </label>
                                <input
                                  id="contactEmail"
                                  type="email"
                                  value={brandingForm.contact_email}
                                  onChange={(e) => setBrandingForm((prev) => ({ ...prev, contact_email: e.target.value }))}
                                  placeholder="info@pharmacy.com"
                                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="contactPhone">
                                  Contact phone
                                </label>
                                <PhoneInput
                                  id="contactPhone"
                                  name="contactPhone"
                                  value={brandingForm.contact_phone}
                                  onChange={(next) => setBrandingForm((prev) => ({ ...prev, contact_phone: next }))}
                                  placeholder="Enter phone number"
                                  className="text-sm"
                                />
                              </div>
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="contactAddress">
                                Contact address
                              </label>
                              <textarea
                                id="contactAddress"
                                rows={3}
                                value={brandingForm.contact_address}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, contact_address: e.target.value }))}
                                placeholder="Street, City, Country"
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              />
                            </div>
                          </section>

                          <section id="branding-assets" className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                            <div>
                              <div className="text-sm font-semibold text-slate-900">Media</div>
                              <p className="text-xs text-slate-500 mt-1">Upload brand images for the storefront header.</p>
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="logoUrl">
                                Logo URL
                              </label>
                              <input
                                id="logoUrl"
                                value={brandingForm.logo_url}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, logo_url: e.target.value }))}
                                placeholder="https://.../logo.png"
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              />
                            </div>

                            <div>
                              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="heroImageUrl">
                                Hero image URL
                              </label>
                              <input
                                id="heroImageUrl"
                                value={brandingForm.hero_image_url}
                                onChange={(e) => setBrandingForm((prev) => ({ ...prev, hero_image_url: e.target.value }))}
                                placeholder="https://.../hero.jpg"
                                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                              />
                            </div>
                          </section>
                        </div>

                        <aside className="space-y-4 lg:sticky lg:top-6">
                          <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4 shadow-sm">
                            <div className="text-sm font-semibold text-slate-900">Live preview</div>
                            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-3">
                              <div className="flex items-center gap-3">
                                <div
                                  className="w-12 h-12 rounded-2xl flex items-center justify-center text-white text-sm font-semibold"
                                  style={{ backgroundColor: brandingForm.primary_color || "#4f46e5" }}
                                >
                                  {pharmacy?.name ? pharmacy.name.slice(0, 2).toUpperCase() : "PH"}
                                </div>
                                <div>
                                  <div className="text-sm font-semibold text-slate-900">{pharmacy?.name ?? "Your pharmacy"}</div>
                                  <div className="text-xs text-slate-500">Theme: {brandingForm.theme_preset}</div>
                                </div>
                              </div>
                              <div className="text-xs text-slate-600">
                                {brandingForm.branding_details || "Add a short description to introduce your pharmacy."}
                              </div>
                              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                                <span className="inline-flex items-center gap-1">
                                  <span
                                    className="w-3 h-3 rounded-full border border-slate-200"
                                    style={{ backgroundColor: brandingForm.primary_color || "#4f46e5" }}
                                  />
                                  Primary
                                </span>
                                <span className="inline-flex items-center gap-1">
                                  <span
                                    className="w-3 h-3 rounded-full border border-slate-200"
                                    style={{ backgroundColor: brandingForm.accent_color || "#3b82f6" }}
                                  />
                                  Accent
                                </span>
                              </div>
                            </div>
                            <div className="text-xs text-slate-500 space-y-2">
                              <div>Layout: {brandingForm.storefront_layout}</div>
                              <div>Font: {brandingForm.font_family || "Default"}</div>
                              <div>COD: {brandingForm.support_cod ? "Enabled" : "Disabled"}</div>
                            </div>
                          </div>
                          {isBrandingDirty ? (
                            <div className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs text-blue-700">
                              You have unsaved changes. Save to update your storefront.
                            </div>
                          ) : null}
                        </aside>
                      </div>

                    </form>
                    <div className="sticky bottom-6 z-10">
                      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 shadow-lg backdrop-blur">
                        <div className="text-xs text-slate-600">
                          {isBrandingDirty ? "Unsaved changes" : "All changes saved"}
                        </div>
                        <button
                          type="submit"
                          form="branding-form"
                          disabled={!isBrandingDirty}
                          className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
                        >
                          Save branding
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            ) : (
              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h2 className="text-lg font-semibold text-slate-900">Pharmacy branding</h2>
                <p className="text-sm text-slate-500 mt-1">Sign in as an owner to customize a pharmacy storefront.</p>
                <p className="text-sm text-slate-600 mt-4">
                  Admins can approve pharmacies, but branding is managed by the pharmacy owner account.
                </p>
              </section>
            )}

            <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-6 py-5 border-b border-slate-200">
                <h2 className="text-lg font-semibold text-slate-900">Change password</h2>
                <p className="text-sm text-slate-500 mt-1">
                  Signed in as{" "}
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-700">
                    {user?.email ?? "user"}
                  </span>
                  .
                </p>
              </div>

              <div className="px-6 py-5">
                <form className="space-y-4" onSubmit={submitChangePassword}>
                  {changeError ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{changeError}</div>
                  ) : null}
                  {changeSuccess ? (
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
                      {changeSuccess}
                    </div>
                  ) : null}

                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="currentPassword">
                      Current password
                    </label>
                    <input
                      id="currentPassword"
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      required
                      className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="newPassword">
                      New password
                    </label>
                    <input
                      id="newPassword"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      minLength={8}
                      className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                    />
                    <p className="text-xs text-slate-500 mt-2">Minimum 8 characters.</p>
                  </div>

                  <button type="submit" className="w-full sm:w-auto px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700">
                    Update password
                  </button>
                </form>
              </div>
            </section>

            {isAdmin ? (
              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-5 border-b border-slate-200">
                  <h2 className="text-lg font-semibold text-slate-900">Admin reset password</h2>
                  <p className="text-sm text-slate-500 mt-1">Reset an owner/admin password by email.</p>
                </div>

                <div className="px-6 py-5">
                  <form className="space-y-4" onSubmit={submitAdminReset}>
                    {resetError ? (
                      <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{resetError}</div>
                    ) : null}
                    {resetSuccess ? (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
                        {resetSuccess}
                      </div>
                    ) : null}

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="resetEmail">
                          User email
                        </label>
                        <input
                          id="resetEmail"
                          type="email"
                          value={resetEmail}
                          onChange={(e) => setResetEmail(e.target.value)}
                          placeholder="owner@example.com"
                          required
                          className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="resetPassword">
                          New password
                        </label>
                        <input
                          id="resetPassword"
                          type="password"
                          value={resetNewPassword}
                          onChange={(e) => setResetNewPassword(e.target.value)}
                          required
                          minLength={8}
                          className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100 text-sm"
                        />
                      </div>
                    </div>

                    <button type="submit" className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700">
                      Reset password
                    </button>
                  </form>
                </div>
              </section>
            ) : (
              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h2 className="text-lg font-semibold text-slate-900">Need help?</h2>
                <p className="text-sm text-slate-500 mt-1">If you forget your password, ask an admin to reset it.</p>
                <p className="text-sm text-slate-600 mt-4">There is no email-based password recovery yet.</p>
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
