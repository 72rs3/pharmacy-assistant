export default function PortalAuthLayout({ children }) {
  return (
    <div className="portal-auth">
      <main className="portal-auth-inner">
        <div className="portal-auth-card">
          <div className="portal-auth-logo">
            <div className="portal-auth-mark">
              <span className="portal-auth-pill"></span>
            </div>
            <div>
              <div className="portal-auth-title">MediTrack</div>
              <div className="portal-auth-subtitle">Manage your pharmacy smarter</div>
            </div>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
