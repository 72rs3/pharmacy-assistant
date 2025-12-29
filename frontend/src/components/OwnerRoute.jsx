import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function OwnerRoute({ children }) {
  const { token, user, isLoadingUser } = useAuth();

  if (!token) {
    return <Navigate to="/portal/login" replace />;
  }

  if (isLoadingUser) {
    return null;
  }

  if (!user?.pharmacy_id || user?.is_admin) {
    return <Navigate to="/portal" replace />;
  }

  return children;
}

