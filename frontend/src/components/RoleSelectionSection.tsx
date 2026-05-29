"use client";

import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { GraduationCap, Landmark, Loader2, AlertTriangle, ChevronRight, ChevronLeft, User, Building2, BookOpen } from "lucide-react";

export const RoleSelectionSection: React.FC = () => {
  const { user: authUser, selectRole, loading, error } = useAuth();
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedRole, setSelectedRole] = useState<"student" | "instructor" | null>(null);
  const [formData, setFormData] = useState({
    displayName: authUser?.displayName || "",
    institution: "",
    department: "",
  });

  const handleNext = () => {
    if (selectedRole) setStep(2);
  };

  const handleBack = () => {
    setStep(1);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedRole) {
      selectRole(selectedRole, formData);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#fbfaf7] px-4">
      <div className="w-full max-w-md">

        {/* Header */}
        <div className="text-center mb-10">
          <div className="w-12 h-12 rounded-2xl bg-[#1c1c18] flex items-center justify-center mx-auto mb-4 shadow-lg">
            <span className="text-white font-bold text-lg font-mono">G</span>
          </div>
          <h1 className="text-2xl font-bold text-[#1c1c18] font-display">
            {step === 1 ? "Welcome to GradeWise" : "Complete Your Profile"}
          </h1>
          <p className="text-sm text-[#5e5c54] mt-2">
            {step === 1 
              ? "Select your role to continue. This is stored securely in the database." 
              : "Tell us a bit more about yourself to personalize your experience."}
          </p>
        </div>

        {step === 1 && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => setSelectedRole("student")}
                className={`group flex flex-col items-center gap-4 p-6 rounded-2xl border-2 transition-all cursor-pointer ${
                  selectedRole === "student" 
                    ? "border-violet-600 bg-violet-50/50 shadow-sm" 
                    : "border-[#dfdbd3] bg-white hover:border-[#1c1c18] hover:shadow-md"
                }`}
              >
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${
                  selectedRole === "student" ? "bg-violet-600" : "bg-violet-50 group-hover:bg-violet-100"
                }`}>
                  <GraduationCap className={`w-6 h-6 ${selectedRole === "student" ? "text-white" : "text-violet-700"}`} />
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-[#1c1c18]">Student</p>
                  <p className="text-[11px] text-[#8e8b80] mt-0.5 leading-relaxed">
                    Submit assignments and view AI feedback
                  </p>
                </div>
              </button>

              <button
                onClick={() => setSelectedRole("instructor")}
                className={`group flex flex-col items-center gap-4 p-6 rounded-2xl border-2 transition-all cursor-pointer ${
                  selectedRole === "instructor" 
                    ? "border-green-600 bg-green-50/50 shadow-sm" 
                    : "border-[#dfdbd3] bg-white hover:border-[#1c1c18] hover:shadow-md"
                }`}
              >
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${
                  selectedRole === "instructor" ? "bg-green-600" : "bg-green-50 group-hover:bg-green-100"
                }`}>
                  <Landmark className={`w-6 h-6 ${selectedRole === "instructor" ? "text-white" : "text-green-700"}`} />
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-[#1c1c18]">Instructor</p>
                  <p className="text-[11px] text-[#8e8b80] mt-0.5 leading-relaxed">
                    Manage subjects, upload references, grade batches
                  </p>
                </div>
              </button>
            </div>

            <button
              onClick={handleNext}
              disabled={!selectedRole}
              className="w-full flex items-center justify-center gap-2 bg-[#1c1c18] text-white py-3.5 px-4 rounded-xl font-bold text-sm hover:bg-[#2c2c28] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Continue
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {step === 2 && (
          <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-2xl border border-[#eae7e1] shadow-sm">
            
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-[#1c1c18] uppercase tracking-wider flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-[#8e8b80]" /> Full Name
              </label>
              <input
                type="text"
                required
                value={formData.displayName}
                onChange={(e) => setFormData({ ...formData, displayName: e.target.value })}
                className="w-full bg-[#fbfaf7] border border-[#dfdbd3] rounded-lg px-3.5 py-2.5 text-sm focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition-all"
                placeholder="Enter your full name"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-[#1c1c18] uppercase tracking-wider flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-[#8e8b80]" /> Institution / University
              </label>
              <input
                type="text"
                required
                value={formData.institution}
                onChange={(e) => setFormData({ ...formData, institution: e.target.value })}
                className="w-full bg-[#fbfaf7] border border-[#dfdbd3] rounded-lg px-3.5 py-2.5 text-sm focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition-all"
                placeholder="e.g. Stanford University"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-[#1c1c18] uppercase tracking-wider flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-[#8e8b80]" /> Department / Major
              </label>
              <input
                type="text"
                required
                value={formData.department}
                onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                className="w-full bg-[#fbfaf7] border border-[#dfdbd3] rounded-lg px-3.5 py-2.5 text-sm focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition-all"
                placeholder="e.g. Computer Science"
              />
            </div>

            <div className="pt-4 flex gap-3">
              <button
                type="button"
                onClick={handleBack}
                disabled={loading}
                className="flex items-center justify-center gap-1 bg-[#fbfaf7] border border-[#dfdbd3] text-[#1c1c18] py-3.5 px-4 rounded-xl font-bold text-sm hover:bg-[#f4f2eb] transition-colors disabled:opacity-50 flex-1"
              >
                <ChevronLeft className="w-4 h-4" />
                Back
              </button>
              <button
                type="submit"
                disabled={loading || !formData.displayName || !formData.institution || !formData.department}
                className="flex items-center justify-center gap-2 bg-violet-600 text-white py-3.5 px-4 rounded-xl font-bold text-sm hover:bg-violet-700 transition-colors disabled:opacity-50 flex-2 w-full"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</>
                ) : (
                  "Complete Setup"
                )}
              </button>
            </div>
          </form>
        )}

        {error && (
          <div className="flex items-start gap-2 mt-4 p-3 rounded-xl bg-red-50 border border-red-200">
            <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
            <p className="text-xs text-red-700">{error}</p>
          </div>
        )}

      </div>
    </div>
  );
};
