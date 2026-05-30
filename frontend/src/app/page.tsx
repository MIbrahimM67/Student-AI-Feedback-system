"use client";

import React from "react";
import { useAuth } from "@/context/AuthContext";
import { LandingSection } from "@/components/LandingSection";
import { RoleSelectionSection } from "@/components/RoleSelectionSection";
import { StudentDashboard } from "@/components/StudentDashboard";
import { InstructorDashboard } from "@/components/InstructorDashboard";
import { AdminDashboard } from "@/components/AdminDashboard";
import { 
  Sparkles, LogOut, Shield, GraduationCap, 
  Landmark, ChevronRight, Terminal, UserCog
} from "lucide-react";
import { ProfileModal } from "@/components/ProfileModal";


export default function Home() {
  const { user, loading, logout } = useAuth();
  const [profileOpen, setProfileOpen] = React.useState(false);


  // Full Screen Monospace IDE Loading Screen
  if (loading) {
    return (
      <div className="min-h-screen flex flex-col justify-center items-center bg-[#fbfaf7] text-[#1c1c18]">
        <div className="flex items-center gap-3 mb-4">
          <Terminal className="w-6 h-6 text-violet-650 animate-pulse" />
          <span className="font-mono text-xs font-bold uppercase tracking-widest text-[#5e5c54]">Hydrating Session Context...</span>
        </div>
        <div className="w-48 bg-[#f4f2eb] h-1 rounded-full overflow-hidden border border-[#dfdbd3]">
          <div className="bg-violet-650 h-full w-2/3 rounded-full animate-pulse-subtle" />
        </div>
      </div>
    );
  }

  // PORTAL ROUTING 1: Non-authenticated Guest Landing
  if (!user) {
    return (
      <main className="min-h-screen flex flex-col bg-[#fbfaf7] text-[#1c1c18]">
        <header className="py-4 px-8 border-b border-[#eae7e1] bg-[#fbfaf7]/80 backdrop-blur-md sticky top-0 z-50">
          <div className="max-w-7xl w-full mx-auto flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-[#1c1c18] rounded-xl shadow-sm">
                <Sparkles className="w-4.5 h-4.5 text-white" />
              </div>
              <span className="font-bold text-sm tracking-tight text-[#1c1c18] uppercase font-mono">
                GradeWise
              </span>
            </div>
            <span className="text-[10px] font-mono font-bold text-[#5e5c54] border border-[#dfdbd3] py-1 px-3.5 rounded-full uppercase tracking-wider bg-[#f4f2eb]">
              GradeWise Engine v3.0
            </span>
          </div>
        </header>
        
        <LandingSection />
      </main>
    );
  }

  // Determine current active dashboard role strictly based on user auth role claim
  const activeRole = user.role;
  
  if (!activeRole) {
    return (
      <main className="min-h-screen flex flex-col bg-[#fbfaf7] text-[#1c1c18]">
        <RoleSelectionSection />
      </main>
    );
  }

  // Helper metadata styling for active sidebar nodes
  const getSidebarMeta = (role: string) => {
    switch (role) {
      case "admin":
        return { label: "Admin Suite", icon: <Shield className="w-4 h-4" />, border: "border-rose-355", text: "text-red-750 bg-red-100 border-red-200" };
      case "instructor":
        return { label: "Faculty Hub", icon: <Landmark className="w-4 h-4" />, border: "border-cyan-355", text: "text-[#15803d] bg-green-50 border-green-200" };
      default:
        return { label: "Student Console", icon: <GraduationCap className="w-4 h-4" />, border: "border-violet-355", text: "text-violet-750 bg-violet-50 border-violet-200" };
    }
  };

  const currentMeta = getSidebarMeta(activeRole);

  return (
    <div className="min-h-screen flex bg-[#fbfaf7] text-[#1c1c18] overflow-hidden">
      
      {/* --- SIDEBAR PANEL (250px fixed) --- */}
      <aside className="hidden lg:flex flex-col w-[250px] bg-[#f5f3ef] border-r border-[#eae7e1] relative z-40 shrink-0 select-none">
        
        {/* Brand Header */}
        <div className="py-6 px-6 border-b border-[#eae7e1] flex items-center gap-2.5">
          <div className="p-1.5 bg-[#1c1c18] rounded-xl shadow-sm">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <span className="font-extrabold text-xs uppercase tracking-widest font-mono text-[#1c1c18]">
            GradeWise
          </span>
        </div>

        {/* Sidebar Nav Nodes */}
        <div className="flex-1 py-6 px-4 space-y-7">
          <div className="space-y-2">
            <span className="text-[9px] font-bold text-[#8e8b80] uppercase tracking-widest font-mono block px-2">Console Portal</span>
            
            <div className="space-y-1">
              {activeRole === "student" && (
                <div className="w-full flex items-center gap-2.5 py-2.5 px-3 rounded-xl font-bold text-xs bg-white border border-[#dfdbd3] text-[#1c1c18] shadow-sm">
                  <GraduationCap className="w-4 h-4 text-violet-650" />
                  Student Console
                </div>
              )}

              {activeRole === "instructor" && (
                <div className="w-full flex items-center gap-2.5 py-2.5 px-3 rounded-xl font-bold text-xs bg-white border border-[#dfdbd3] text-[#1c1c18] shadow-sm">
                  <Landmark className="w-4 h-4 text-green-700" />
                  Faculty Hub
                </div>
              )}

              {activeRole === "admin" && (
                <div className="w-full flex items-center gap-2.5 py-2.5 px-3 rounded-xl font-bold text-xs bg-white border border-[#dfdbd3] text-[#1c1c18] shadow-sm">
                  <Shield className="w-4 h-4 text-red-600" />
                  Admin Suite
                </div>
              )}
            </div>
          </div>
        </div>

        {/* User Capsule Footer */}
        <div className="p-4 border-t border-[#eae7e1] bg-[#f5f3ef] space-y-4">
          <button
            onClick={() => setProfileOpen(true)}
            className="w-full flex items-center gap-2.5 p-1.5 rounded-xl bg-white border border-[#dfdbd3] shadow-sm hover:border-[#1c1c18] hover:shadow-md transition-all group cursor-pointer text-left"
            title="Edit profile"
          >
            {user.photoURL ? (
              <img src={user.photoURL} alt={user.displayName} className="w-7 h-7 rounded-lg object-cover" />
            ) : (
              <div className="w-7 h-7 rounded-lg bg-[#1c1c18] text-white font-extrabold flex items-center justify-center text-xs">
                {user.displayName.substring(0, 1).toUpperCase()}
              </div>
            )}
            <div className="flex flex-col text-left truncate flex-1">
              <span className="text-[10px] font-bold text-[#1c1c18] truncate">{user.displayName}</span>
              <span className="text-[8px] text-[#8e8b80] font-mono truncate">{user.email}</span>
            </div>
            <UserCog className="w-3.5 h-3.5 text-[#8e8b80] group-hover:text-[#1c1c18] shrink-0 transition-colors" />
          </button>

          <button
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl border border-[#dfdbd3] hover:border-red-200 hover:bg-red-50 hover:text-red-650 text-[#5e5c54] font-bold text-xs transition-all active:scale-98 cursor-pointer"
          >
            <LogOut className="w-4.5 h-4.5" />
            Sign Out Session
          </button>
        </div>

      </aside>

      {/* --- MAIN DISPLAY WORKSPACE --- */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#fbfaf7]">
        
        {/* Workspace Top Toolbar */}
        <header className="py-4 px-6 border-b border-[#eae7e1] bg-[#fbfaf7]/85 backdrop-blur-md sticky top-0 z-30 flex items-center justify-between gap-4">
          
          {/* Breadcrumb Indicator */}
          <div className="flex items-center gap-2 text-xs font-semibold text-[#8e8b80] font-mono">
            <span>Workspace</span>
            <ChevronRight className="w-3.5 h-3.5 text-[#8e8b80]/60" />
            <span className="text-[#1c1c18] font-bold">{currentMeta.label}</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Display active console badge */}
            <div className={`py-1 px-3.5 rounded-full border text-[9px] font-bold tracking-widest uppercase flex items-center gap-1.5 shadow-2xs ${currentMeta.text}`}>
              {currentMeta.icon}
              {currentMeta.label}
            </div>
          </div>

        </header>

        {/* Portal dashboard displays */}
        <div className="flex-1 flex flex-col bg-[#fbfaf7]">
          {activeRole === "student" && <StudentDashboard />}
          {activeRole === "instructor" && <InstructorDashboard />}
          {activeRole === "admin" && <AdminDashboard />}
        </div>

      </div>

    </div>

    {/* Profile edit modal — accessible from sidebar user card */}
    <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
  );
}
