"use client";

import React from "react";
import { useAuth } from "@/context/AuthContext";
import { GraduationCap, Landmark, Loader2, AlertTriangle } from "lucide-react";

export const RoleSelectionSection: React.FC = () => {
  const { selectRole, loading, error } = useAuth();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#fbfaf7] px-4">
      <div className="w-full max-w-md">

        {/* Header */}
        <div className="text-center mb-10">
          <div className="w-12 h-12 rounded-2xl bg-[#1c1c18] flex items-center justify-center mx-auto mb-4 shadow-lg">
            <span className="text-white font-bold text-lg font-mono">G</span>
          </div>
          <h1 className="text-2xl font-bold text-[#1c1c18] font-display">Welcome to GradeWise</h1>
          <p className="text-sm text-[#5e5c54] mt-2">
            Select your role to continue. This is stored securely in the database.
          </p>
        </div>

        {/* Role Cards */}
        <div className="grid grid-cols-2 gap-4">
          <button
            id="role-student"
            onClick={() => selectRole("student")}
            disabled={loading}
            className="group flex flex-col items-center gap-4 p-6 rounded-2xl border-2 border-[#dfdbd3] bg-white hover:border-[#1c1c18] hover:shadow-md transition-all cursor-pointer disabled:opacity-50"
          >
            <div className="w-12 h-12 rounded-xl bg-violet-50 flex items-center justify-center group-hover:bg-violet-100 transition-colors">
              <GraduationCap className="w-6 h-6 text-violet-700" />
            </div>
            <div className="text-center">
              <p className="text-sm font-bold text-[#1c1c18]">Student</p>
              <p className="text-[11px] text-[#8e8b80] mt-0.5 leading-relaxed">
                Submit assignments and view AI feedback
              </p>
            </div>
          </button>

          <button
            id="role-instructor"
            onClick={() => selectRole("instructor")}
            disabled={loading}
            className="group flex flex-col items-center gap-4 p-6 rounded-2xl border-2 border-[#dfdbd3] bg-white hover:border-[#1c1c18] hover:shadow-md transition-all cursor-pointer disabled:opacity-50"
          >
            <div className="w-12 h-12 rounded-xl bg-green-50 flex items-center justify-center group-hover:bg-green-100 transition-colors">
              <Landmark className="w-6 h-6 text-green-700" />
            </div>
            <div className="text-center">
              <p className="text-sm font-bold text-[#1c1c18]">Instructor</p>
              <p className="text-[11px] text-[#8e8b80] mt-0.5 leading-relaxed">
                Manage subjects, upload references, grade batches
              </p>
            </div>
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center gap-2 mt-6 text-xs text-[#5e5c54]">
            <Loader2 className="w-4 h-4 animate-spin" />
            Setting up your account...
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 mt-4 p-3 rounded-xl bg-red-50 border border-red-200">
            <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
            <p className="text-xs text-red-700">{error}</p>
          </div>
        )}

        <p className="text-center text-[10px] text-[#8e8b80] mt-8">
          Role is saved permanently in the database — you can change it later from settings.
        </p>
      </div>
    </div>
  );
};
