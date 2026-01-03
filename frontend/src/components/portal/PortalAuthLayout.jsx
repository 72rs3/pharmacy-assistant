export default function PortalAuthLayout({ children }) {
  const portalLogoUrl = import.meta.env.VITE_PORTAL_LOGO_URL ?? "/online-genius.png";

  return (
    <div className="portal-auth">
      <main className="portal-auth-inner">
        <div className="portal-auth-card">
          <div className="portal-auth-logo">
            <div
              className={
                portalLogoUrl ? "portal-auth-mark portal-auth-mark--image" : "portal-auth-mark"
              }
            >
              {portalLogoUrl ? (
                <img className="portal-auth-logo-image" src={portalLogoUrl} alt="Online Genius" />
              ) : (
                <span className="portal-auth-pill"></span>
              )}
            </div>
            <div>
              <div className="portal-auth-title">Online Genius</div>
              <div className="portal-auth-subtitle">Manage your pharmacy smarter</div>
            </div>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
