"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import {
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onAuthStateChanged,
  User as FirebaseUser,
  getIdToken,
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import axios from "axios";
import { API_URL } from "@/lib/api-config";

export interface UserProfile {
  uid: string;
  email: string;
  displayName: string;
  photoURL?: string;
  role: "student" | "instructor" | "admin" | "";
  facultyStatus: "none" | "pending" | "approved" | "rejected";
  proStatus: "active" | "inactive";
  warningCount: number;
  blockedUntil?: string | null;
  createdAt: string;
  updatedAt: string;
}

interface AuthContextType {
  user: UserProfile | null;
  firebaseUser: FirebaseUser | null;
  loading: boolean;
  error: string | null;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  selectRole: (role: "student" | "instructor", profileData?: { displayName?: string; institution?: string; department?: string }) => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Sync Firebase user with Postgres via backend
  const syncBackendProfile = async (fbUser: FirebaseUser) => {
    try {
      const token = await getIdToken(fbUser);
      const response = await axios.post(
        `${API_URL}/api/auth/sync-user`,
        {
          email: fbUser.email || "",
          displayName: fbUser.displayName || "User",
          photoURL: fbUser.photoURL || "",
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const backendUser = response.data.user;
      setUser({
        uid: backendUser.uid,
        email: backendUser.email,
        displayName: backendUser.display_name || "User",
        photoURL: backendUser.photo_url || "",
        role: backendUser.role,
        facultyStatus: backendUser.faculty_status,
        proStatus: backendUser.pro_status,
        warningCount: backendUser.warning_count,
        blockedUntil: backendUser.blocked_until,
        createdAt: backendUser.created_at,
        updatedAt: backendUser.updated_at,
      });
      setError(null);
    } catch (err: any) {
      console.error("Backend sync failed:", err);
      const errMsg = err.response?.data?.detail || err.message || "Unknown error";
      setError(err.response?.status === 403 ? errMsg : `Unable to open your workspace: ${errMsg}`);
      setUser(null);
    }
  };

  useEffect(() => {
    if (!auth) {
      setLoading(false);
      return;
    }
    const unsubscribe = onAuthStateChanged(auth, async (fbUser) => {
      setLoading(true);
      if (fbUser) {
        setFirebaseUser(fbUser);
        await syncBackendProfile(fbUser);
      } else {
        setFirebaseUser(null);
        setUser(null);
      }
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const loginWithGoogle = async () => {
    setLoading(true);
    setError(null);
    try {
      if (!auth) throw new Error("Firebase Auth not initialized.");
      const provider = new GoogleAuthProvider();
      const result = await signInWithPopup(auth, provider);
      setFirebaseUser(result.user);
      await syncBackendProfile(result.user);
    } catch (err: any) {
      setError(err.message || "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      if (auth) await signOut(auth);
      setUser(null);
      setFirebaseUser(null);
    } catch (err: any) {
      console.error("Logout failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const selectRole = async (role: "student" | "instructor", profileData?: { displayName?: string; institution?: string; department?: string }) => {
    if (!firebaseUser) return;
    setLoading(true);
    try {
      const token = await getIdToken(firebaseUser);
      const payload = {
        role,
        display_name: profileData?.displayName,
        institution: profileData?.institution,
        department: profileData?.department
      };
      
      const response = await axios.post(
        `${API_URL}/api/auth/select-role`,
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const backendUser = response.data.user;
      setUser({
        uid: backendUser.uid,
        email: backendUser.email,
        displayName: backendUser.display_name || "User",
        photoURL: backendUser.photo_url || "",
        role: backendUser.role,
        facultyStatus: backendUser.faculty_status,
        proStatus: backendUser.pro_status,
        warningCount: backendUser.warning_count,
        blockedUntil: backendUser.blocked_until,
        createdAt: backendUser.created_at,
        updatedAt: backendUser.updated_at,
      });
      setError(null);
    } catch (err: any) {
      console.error("Role selection failed:", err);
      setError("Failed to set role. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const refreshProfile = async () => {
    if (firebaseUser) {
      await syncBackendProfile(firebaseUser);
    }
  };

  return (
    <AuthContext.Provider value={{ user, firebaseUser, loading, error, loginWithGoogle, logout, selectRole, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
