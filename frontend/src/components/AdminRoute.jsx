import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function AdminRoute({ children }) {
  const { token, isAdmin, isLoadingUser } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (isLoadingUser) {
    return null;
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return children;
}

