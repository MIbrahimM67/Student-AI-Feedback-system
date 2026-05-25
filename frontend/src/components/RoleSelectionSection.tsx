"use client";

import React from "react";
import { useAuth } from "@/context/AuthContext";
import { GraduationCap, Landmark, Sparkles } from "lucide-react";

export const RoleSelectionSection: React.FC = () => {
  const { selectRole, loading, error, user } = useAuth();

  return (
    <div className="flex-1 flex flex-col justify-center items-center px-6 relative overflow-hidden py-16 bg-[#fbfaf7]">
      {/* Dynamic Warm Glow Backdrops */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[35rem] h-[35rem] bg-amber-500/5 rounded-full blur-[120px] -z-10" />
      
      <div className="max-w-xl w-full text-center space-y-7 z-10">
        
        {/* Onboarding Badge */}
        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#f4f2eb] border border-[#dfdbd3] text-[#5e5c54] text-xs font-bold animate-float">
          <Sparkles className="w-3.5 h-3.5 text-amber-600" />
          Onboarding Profile Setup
        </div>

        {/* Dynamic Greeting */}
        <div className="space-y-3">
          <h1 className="text-3xl md:text-4xl font-extrabold text-[#1c1c18] font-display tracking-tight">
            Welcome, {user?.displayName || "Academic User"}
          </h1>
          <p className="text-[#5e5c54] text-sm max-w-sm mx-auto font-sans font-medium leading-relaxed">
            Choose your core portal interface. This setting directs your dashboard consoles and privileges.
          </p>
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-750 text-xs font-bold leading-relaxed">
            {error}
          </div>
        )}

        {/* Roles Selection Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
          
          {/* Option: Student Console */}
          <button
            onClick={() => selectRole("student")}
            disabled={loading}
            className="group dev-card bg-white p-8 rounded-3xl border border-[#dfdbd3] hover:border-violet-500 hover:shadow-lg transition-all duration-300 flex flex-col items-center text-center cursor-pointer disabled:pointer-events-none disabled:opacity-50"
          >
            <div className="p-4 bg-violet-50 border border-violet-200 text-violet-700 rounded-2xl mb-5 group-hover:scale-105 transition-all duration-300">
              <GraduationCap className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-[#1c1c18] font-display mb-2">Student Portal</h3>
            <p className="text-xs text-[#5e5c54] leading-relaxed font-sans font-medium">
              Submit essays, programming codes, or handwriting scans to receive detailed automated reports.
            </p>
          </button>

          {/* Option: Instructor Console */}
          <button
            onClick={() => selectRole("instructor")}
            disabled={loading}
            className="group dev-card bg-white p-8 rounded-3xl border border-[#dfdbd3] hover:border-cyan-500 hover:shadow-lg transition-all duration-300 flex flex-col items-center text-center cursor-pointer disabled:pointer-events-none disabled:opacity-50"
          >
            <div className="p-4 bg-cyan-50 border border-cyan-200 text-cyan-700 rounded-2xl mb-5 group-hover:scale-105 transition-all duration-300">
              <Landmark className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-[#1c1c18] font-display mb-2">Instructor Hub</h3>
            <p className="text-xs text-[#5e5c54] leading-relaxed font-sans font-medium">
              Upload class batches, check plagiarism metrics, customize rubrics, and export aggregated grade sheets.
            </p>
          </button>

        </div>
      </div>
    </div>
  );
};
