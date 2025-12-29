import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function AdminRoute({ children }) {
  const { token, isAdmin, isLoadingUser } = useAuth();

  if (!token) {
    return <Navigate to="/portal/login" replace />;
  }

  if (isLoadingUser) {
    return null;
  }

  if (!isAdmin) {
    return <Navigate to="/portal" replace />;
  }

  return children;
}

