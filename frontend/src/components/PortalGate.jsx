import { Navigate } from "react-router-dom";
import { isPortalHost } from "../utils/tenant";

export default function PortalGate({ children }) {
  if (!isPortalHost()) {
    return <Navigate to="/" replace />;
  }

  return children;
}

