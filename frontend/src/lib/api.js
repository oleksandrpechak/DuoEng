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
  const token = localStorage.getItem('accessToken');
  const userId = localStorage.getItem('userId');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Optionally attach userId if needed elsewhere
  // config.headers['X-User-Id'] = userId;
  return config;
});

// Handle 401 (expired / invalid token) globally — clear auth and redirect
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      const detail = error.response.data?.detail || "";
      if (detail === "Token expired" || detail === "Invalid token" || detail === "Player not found") {
        localStorage.removeItem("accessToken");
        localStorage.removeItem("userId");
        localStorage.removeItem("nickname");
        localStorage.removeItem("authType");
        localStorage.removeItem("duoeng_platform_stats");
        // Redirect to landing page to re-authenticate
        if (window.location.pathname !== "/") {
          window.location.href = "/";
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
