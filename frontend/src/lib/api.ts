import axios from "axios";
import { auth } from "./firebase";
import { getIdToken } from "firebase/auth";

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json"
  }
});

// Request Interceptor to append Authorization JWT tokens
api.interceptors.request.use(
  async (config) => {
    // 1. Check if Firebase auth client is initialized and a user is signed in
    if (auth && auth.currentUser) {
      try {
        const token = await getIdToken(auth.currentUser);
        config.headers.Authorization = `Bearer ${token}`;
      } catch (error) {
        console.error("Failed to append Firebase Auth Token:", error);
      }
    } 
    // 2. Fallback to mock session tokens if running simulated frontend context
    else {
      // Look up if a mock UID is stored in local storage to identify mock actor role
      if (typeof window !== "undefined") {
        const mockRole = localStorage.getItem("mock_user_role");
        if (mockRole) {
          config.headers.Authorization = `Bearer mock_${mockRole}_token`;
        }
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response Interceptor to centralize error logging
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const fallbackMsg = "An error has occurred connecting to the backend.";
    const detail = error.response?.data?.detail || fallbackMsg;
    
    // Package errors standardly
    const packagedError = {
      status: error.response?.status || 500,
      message: typeof detail === "string" ? detail : JSON.stringify(detail),
      original: error
    };
    
    console.error("[API Error Interceptor]:", packagedError);
    return Promise.reject(packagedError);
  }
);

export default api;
export { API_URL };
