/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import api from "../api/axios";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [isLoadingUser, setIsLoadingUser] = useState(false);

  const login = (newToken) => {
    setToken(newToken);
    localStorage.setItem("token", newToken);
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem("token");
    localStorage.removeItem("pharmacy_id");
    localStorage.removeItem("pharmacy_domain");
  };

  useEffect(() => {
    let isActive = true;

    const loadUser = async () => {
      if (!token) {
        setUser(null);
        return;
      }

      setIsLoadingUser(true);
      try {
        const response = await api.get("/auth/me");
        if (isActive) {
          const nextUser = response.data;
          setUser(nextUser);
          if (nextUser?.pharmacy_id) {
            localStorage.setItem("pharmacy_id", String(nextUser.pharmacy_id));
          } else {
            localStorage.removeItem("pharmacy_id");
          }
        }
      } catch {
        if (isActive) {
          setUser(null);
          setToken(null);
          localStorage.removeItem("token");
          localStorage.removeItem("pharmacy_id");
        }
      } finally {
        if (isActive) setIsLoadingUser(false);
      }
    };

    loadUser();
    return () => {
      isActive = false;
    };
  }, [token]);

  const value = useMemo(
    () => ({
      token,
      user,
      isLoadingUser,
      isAdmin: Boolean(user?.is_admin),
      isOwner: Boolean(user?.pharmacy_id) && !user?.is_admin,
      login,
      logout,
    }),
    [token, user, isLoadingUser]
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
