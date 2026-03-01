import axios from "axios";

/**
 * Derive the backend URL.
 *
 * Priority:
 *   1. REACT_APP_BACKEND_URL env-var (baked at build time)
 *   2. Auto-detect: if the frontend is hosted on *.onrender.com,
 *      assume the backend is at the same domain with "-frontend"
 *      replaced by "-backend".
 *   3. Fallback to localhost for local development.
 */
function resolveBackendUrl() {
  if (process.env.REACT_APP_BACKEND_URL) {
    return process.env.REACT_APP_BACKEND_URL;
  }

  const { hostname } = window.location;

  // Auto-detect Render deployment: duoeng-frontend.onrender.com → duoeng-backend.onrender.com
  if (hostname.endsWith(".onrender.com")) {
    const backendHost = hostname.replace("-frontend", "-backend");
    return `https://${backendHost}`;
  }

  return "http://localhost:8000";
}

const rawApiUrl = resolveBackendUrl();

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
