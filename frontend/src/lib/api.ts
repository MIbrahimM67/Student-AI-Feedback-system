import axios from "axios";
import { auth } from "./firebase";
import { getIdToken } from "firebase/auth";

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// Attach real Firebase JWT to every request
api.interceptors.request.use(
  async (config) => {
    // If sending FormData, remove the global JSON content-type so the browser
    // can automatically set multipart/form-data with the correct boundary.
    if (config.data instanceof FormData) {
      delete config.headers["Content-Type"];
    }

    if (auth?.currentUser) {
      try {
        const token = await getIdToken(auth.currentUser);
        config.headers.Authorization = `Bearer ${token}`;
      } catch (e) {
        console.error("Failed to get Firebase token:", e);
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Standardise error shape
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail || "An error occurred connecting to the server.";
    return Promise.reject({
      status: error.response?.status || 500,
      message: typeof detail === "string" ? detail : JSON.stringify(detail),
      original: error,
    });
  }
);

export default api;
export { API_URL };
