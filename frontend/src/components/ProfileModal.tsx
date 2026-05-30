"use client";

import React, { useState, useEffect, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  X, User, Building2, BookOpen, Briefcase, Layers,
  CheckCircle2, AlertTriangle, Loader2, Save, GraduationCap,
  Shield, Landmark, ChevronDown,
} from "lucide-react";

interface FullProfile {
  uid: string;
  email: string;
  display_name: string;
  photo_url: string;
  role: string;
  faculty_status: string;
  pro_status: string;
  warning_count: number;
  created_at: string;
  // Role-specific
  institution?: string;
  department?: string;
  designation?: string;
  teaching_level?: string;
  grading_style?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

const GRADING_STYLE_OPTIONS = [
  { value: "strict",   label: "Strict",   desc: "Rewards precision, penalises every gap" },
  { value: "balanced", label: "Balanced", desc: "Fair weighting of effort and accuracy" },
  { value: "lenient",  label: "Lenient",  desc: "Encourages partial credit generously" },
];

const ROLE_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  admin:      { label: "Admin",      icon: <Shield className="w-3 h-3" />,       color: "bg-rose-50 text-rose-700 border-rose-200" },
  instructor: { label: "Instructor", icon: <Landmark className="w-3 h-3" />,     color: "bg-green-50 text-green-700 border-green-200" },
  student:    { label: "Student",    icon: <GraduationCap className="w-3 h-3" />, color: "bg-blue-50 text-blue-700 border-blue-200" },
};

export const ProfileModal: React.FC<Props> = ({ open, onClose }) => {
  const { user, firebaseUser, refreshProfile } = useAuth();

  const [profile, setProfile] = useState<FullProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [displayName, setDisplayName] = useState("");
  const [institution, setInstitution] = useState("");
  const [department, setDepartment] = useState("");
  const [designation, setDesignation] = useState("");
  const [teachingLevel, setTeachingLevel] = useState("");
  const [gradingStyle, setGradingStyle] = useState("balanced");

  const overlayRef = useRef<HTMLDivElement>(null);

  // Fetch full profile when modal opens
  useEffect(() => {
    if (!open || !user) return;
    setLoading(true);
    setError(null);
    setSuccess(false);
    api.get("/api/auth/profile")
      .then((res) => {
        const p: FullProfile = res.data.profile;
        setProfile(p);
        setDisplayName(p.display_name || "");
        setInstitution(p.institution || "");
        setDepartment(p.department || "");
        setDesignation(p.designation || "");
        setTeachingLevel(p.teaching_level || "");
        setGradingStyle(p.grading_style || "balanced");
      })
      .catch((err) => {
        setError(err.response?.data?.detail || "Failed to load profile.");
      })
      .finally(() => setLoading(false));
  }, [open, user]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const payload: Record<string, string | undefined> = {
        display_name: displayName.trim() || undefined,
        institution:  institution.trim() || undefined,
        department:   department.trim() || undefined,
      };
      if (profile?.role === "instructor" || profile?.role === "admin") {
        payload.designation    = designation.trim() || undefined;
        payload.teaching_level = teachingLevel.trim() || undefined;
        payload.grading_style  = gradingStyle || undefined;
      }
      await api.patch("/api/auth/profile", payload);
      await refreshProfile(); // Refresh global context so display name updates immediately everywhere
      setSuccess(true);
      // Refresh local modal state
      if (profile) {
        setProfile({ ...profile, display_name: displayName, institution, department, designation, teaching_level: teachingLevel, grading_style: gradingStyle });
      }
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to save profile.");
    } finally {
      setSaving(false);
    }
  };

  // Close on overlay click
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  if (!open) return null;

  const roleMeta = ROLE_META[profile?.role || user?.role || "student"];
  const isInstructor = profile?.role === "instructor" || profile?.role === "admin";

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <div className="relative bg-[#fbfaf7] border border-[#eae7e1] rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden animate-fade-in-up">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#eae7e1] bg-[#f5f3ef]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1c1c18] flex items-center justify-center">
              <User className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-[#1c1c18]">Edit Profile</p>
              <p className="text-[10px] text-[#8e8b80]">Update your display name and professional info</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#8e8b80] hover:text-[#1c1c18] hover:bg-[#eae7e1] transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-[#8e8b80]" />
          </div>
        ) : (
          <form onSubmit={handleSave} className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">

            {/* Account info (read-only) */}
            <div className="flex items-center gap-3 p-3 rounded-xl bg-[#f5f3ef] border border-[#eae7e1]">
              {profile?.photo_url ? (
                <img src={profile.photo_url} alt="avatar" className="w-10 h-10 rounded-full object-cover border border-[#dfdbd3]" />
              ) : (
                <div className="w-10 h-10 rounded-full bg-[#1c1c18] flex items-center justify-center text-white font-bold text-sm">
                  {(displayName || user?.displayName || "?")[0].toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-[#1c1c18] truncate">{user?.email}</p>
                <p className="text-[10px] text-[#8e8b80]">Google account — email cannot be changed here</p>
              </div>
              {roleMeta && (
                <span className={`flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${roleMeta.color}`}>
                  {roleMeta.icon} {roleMeta.label}
                </span>
              )}
            </div>

            {/* Banners */}
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200">
                <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
                <p className="text-xs text-red-700">{error}</p>
              </div>
            )}
            {success && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-green-50 border border-green-200">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0 mt-0.5" />
                <p className="text-xs text-green-700 font-semibold">Profile saved successfully!</p>
              </div>
            )}

            {/* Display Name */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest flex items-center gap-1.5">
                <User className="w-3 h-3" /> Display Name
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your full name"
                className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] transition-colors"
              />
            </div>

            {/* Shared fields */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest flex items-center gap-1.5">
                  <Building2 className="w-3 h-3" /> Institution
                </label>
                <input
                  type="text"
                  value={institution}
                  onChange={(e) => setInstitution(e.target.value)}
                  placeholder="University / School"
                  className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] transition-colors"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest flex items-center gap-1.5">
                  <BookOpen className="w-3 h-3" /> Department
                </label>
                <input
                  type="text"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="e.g. Computer Science"
                  className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] transition-colors"
                />
              </div>
            </div>

            {/* Instructor / Admin fields */}
            {isInstructor && (
              <>
                <div className="border-t border-[#eae7e1] pt-4 space-y-4">
                  <p className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest">Faculty Details</p>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest flex items-center gap-1.5">
                        <Briefcase className="w-3 h-3" /> Designation
                      </label>
                      <input
                        type="text"
                        value={designation}
                        onChange={(e) => setDesignation(e.target.value)}
                        placeholder="e.g. Assistant Professor"
                        className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] transition-colors"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest flex items-center gap-1.5">
                        <Layers className="w-3 h-3" /> Teaching Level
                      </label>
                      <input
                        type="text"
                        value={teachingLevel}
                        onChange={(e) => setTeachingLevel(e.target.value)}
                        placeholder="e.g. Undergraduate, Masters"
                        className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] transition-colors"
                      />
                    </div>
                  </div>

                  {/* Grading Style */}
                  <div className="space-y-2">
                    <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest">
                      AI Grading Style Preference
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      {GRADING_STYLE_OPTIONS.map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => setGradingStyle(opt.value)}
                          className={`flex flex-col gap-1 p-3 rounded-xl border text-left transition-all cursor-pointer
                            ${gradingStyle === opt.value
                              ? "border-[#1c1c18] bg-[#1c1c18] text-white"
                              : "border-[#dfdbd3] bg-white text-[#5e5c54] hover:border-[#1c1c18]"
                            }`}
                        >
                          <span className="text-[10px] font-bold">{opt.label}</span>
                          <span className={`text-[9px] leading-relaxed ${gradingStyle === opt.value ? "text-white/70" : "text-[#8e8b80]"}`}>
                            {opt.desc}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2 border-t border-[#eae7e1]">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 py-2.5 rounded-xl border border-[#dfdbd3] bg-[#f5f3ef] text-xs font-bold text-[#1c1c18] hover:bg-[#eae7e1] transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-[#1c1c18] text-white text-xs font-bold hover:bg-[#33332f] transition-colors disabled:opacity-50 cursor-pointer"
              >
                {saving ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving…</>
                ) : (
                  <><Save className="w-3.5 h-3.5" /> Save Changes</>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
