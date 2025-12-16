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
        if (isActive) setUser(response.data);
      } catch {
        if (isActive) {
          setUser(null);
          setToken(null);
          localStorage.removeItem("token");
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
