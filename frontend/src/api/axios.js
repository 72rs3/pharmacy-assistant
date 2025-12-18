import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }

  const domain =
    localStorage.getItem("pharmacy_domain") ||
    (typeof window !== "undefined" ? window.location.hostname?.toLowerCase() : null);
  if (domain) {
    config.headers = config.headers ?? {};
    config.headers["X-Pharmacy-Domain"] = domain;
  }

  const pharmacyId = localStorage.getItem("pharmacy_id");
  if (pharmacyId) {
    config.headers = config.headers ?? {};
    config.headers["X-Pharmacy-ID"] = pharmacyId;
  }

  return config;
});

export default api;
