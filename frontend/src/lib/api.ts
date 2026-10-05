import axios from "axios";
import { auth } from "./firebase";
import { getIdToken } from "firebase/auth";

import { API_URL } from "@/lib/api-config";

const api = axios.create({
  baseURL: API_URL,
});

// Attach real Firebase JWT to every request
api.interceptors.request.use(
  async (config) => {
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
