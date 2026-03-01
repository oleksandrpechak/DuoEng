import axios from "axios";

const rawApiUrl =
  process.env.REACT_APP_BACKEND_URL ||
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
