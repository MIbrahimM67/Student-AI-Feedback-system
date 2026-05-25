"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { 
  signInWithPopup, 
  GoogleAuthProvider, 
  signOut, 
  onAuthStateChanged,
  User as FirebaseUser,
  getIdToken
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import axios from "axios";

// Hydrated User profile format stored in Firestore
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
  selectRole: (role: "student" | "instructor") => Promise<void>;
  useMockAuth: (mockRole: "student" | "instructor" | "admin") => void;
  isMock: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isMock, setIsMock] = useState<boolean>(false);

  // Sync profile document with FastAPI backend
  const syncBackendProfile = async (fbUser: FirebaseUser) => {
    try {
      const token = await getIdToken(fbUser);
      
      const response = await axios.post(
        `${API_URL}/api/auth/sync-user`,
        {
          email: fbUser.email || "student@academic.edu",
          displayName: fbUser.displayName || "Student User",
          photoURL: fbUser.photoURL || ""
        },
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );
      
      setUser(response.data.user);
      setError(null);
    } catch (err: any) {
      console.error("Backend sync failed. Auto-activating development mock profile.", err);
      
      setUser({
        uid: fbUser.uid,
        email: fbUser.email || "student@academic.edu",
        displayName: fbUser.displayName || "Google User",
        photoURL: fbUser.photoURL || "",
        role: "", // Secure default: triggers role setup onboarding
        facultyStatus: "none",
        proStatus: "inactive",
        warningCount: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      });
    }
  };

  useEffect(() => {
    // Return early if no Firebase initialization
    if (!auth) {
      console.warn("Firebase Auth is inactive. Activating mock sandbox environment.");
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
      if (!auth) {
        throw new Error("Firebase Auth was not initialized.");
      }
      const provider = new GoogleAuthProvider();
      const result = await signInWithPopup(auth, provider);
      setFirebaseUser(result.user);
      await syncBackendProfile(result.user);
    } catch (err: any) {
      console.error("Google authentication popup failed: ", err);
      setError(err.message || "Failed to log in with Google.");
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      if (isMock) {
        setIsMock(false);
        setUser(null);
        setFirebaseUser(null);
      } else if (auth) {
        await signOut(auth);
      }
    } catch (err: any) {
      console.error("Logout failed: ", err);
    } finally {
      setLoading(false);
    }
  };

  const selectRole = async (role: "student" | "instructor") => {
    if (!user) return;
    setLoading(true);
    try {
      if (isMock) {
        setUser(prev => prev ? { ...prev, role } : null);
      } else {
        const token = firebaseUser ? await getIdToken(firebaseUser) : "mock_token";
        try {
          const response = await axios.post(
            `${API_URL}/api/auth/select-role`,
            { role },
            {
              headers: {
                Authorization: `Bearer ${token}`
              }
            }
          );
          setUser(response.data.user);
        } catch (apiErr) {
          console.warn("Backend select-role API call failed. Falling back to local state sync.", apiErr);
          // Failsafe local state backup
          setUser(prev => prev ? { ...prev, role } : null);
        }
      }
      setError(null);
    } catch (err: any) {
      console.error("Failed to update user role:", err);
      setError("Failed to select role onboarding.");
    } finally {
      setLoading(false);
    }
  };

  // Development bypass helper
  const useMockAuth = (mockRole: "student" | "instructor" | "admin") => {
    console.log(`Bypassing auth. Logging in as simulated user with role: ${mockRole}`);
    setIsMock(true);
    
    // Seed default settings based on selection
    const mockUser: UserProfile = {
      uid: `mock_${mockRole}_uid`,
      email: `${mockRole}@academic.edu`,
      displayName: mockRole === "admin" ? "System Admin" : (mockRole === "instructor" ? "Dr. Sarah Jenkins" : "Ibrahim Student"),
      role: mockRole,
      facultyStatus: mockRole === "instructor" ? "approved" : "none",
      proStatus: mockRole === "instructor" ? "active" : "inactive",
      warningCount: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    
    setUser(mockUser);
    setLoading(false);
  };

  return (
    <AuthContext.Provider value={{ 
      user, 
      firebaseUser, 
      loading, 
      error, 
      loginWithGoogle, 
      logout, 
      selectRole,
      useMockAuth,
      isMock
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be called within an AuthProvider");
  }
  return context;
};
