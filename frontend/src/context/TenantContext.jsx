/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import api from "../api/axios";
import { isPortalHost } from "../utils/tenant";
import { applyTenantTheme } from "../utils/applyTenantTheme";

const TenantContext = createContext(null);

export function TenantProvider({ children }) {
  const [pharmacy, setPharmacy] = useState(null);
  const [isLoadingTenant, setIsLoadingTenant] = useState(false);
  const [tenantError, setTenantError] = useState("");

  const reloadTenant = async () => {
    if (isPortalHost()) {
      setPharmacy(null);
      setTenantError("");
      return;
    }

    setIsLoadingTenant(true);
    setTenantError("");
    try {
      const res = await api.get("/pharmacies/current");
      setPharmacy(res.data);
      applyTenantTheme(res.data);
    } catch (e) {
      setPharmacy(null);
      setTenantError(e?.response?.data?.detail ?? "Pharmacy not found");
    } finally {
      setIsLoadingTenant(false);
    }
  };

  useEffect(() => {
    reloadTenant();
  }, []);

  const value = useMemo(
    () => ({
      pharmacy,
      isLoadingTenant,
      tenantError,
      reloadTenant,
    }),
    [pharmacy, isLoadingTenant, tenantError]
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  return useContext(TenantContext);
}
