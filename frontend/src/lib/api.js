import axios from "axios";

const rawApiUrl =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) ||
  process.env.REACT_APP_BACKEND_URL ||
  process.env.VITE_API_URL ||
  "http://localhost:8000";

const normalizedApiUrl = rawApiUrl.replace(/\/+$/, "");

const api = axios.create({
  baseURL: `${normalizedApiUrl}/api`,
});

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("accessToken");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
