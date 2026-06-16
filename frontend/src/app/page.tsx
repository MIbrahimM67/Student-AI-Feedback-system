"use client";

import React from "react";
import { useAuth } from "@/context/AuthContext";
import { LandingSection } from "@/components/LandingSection";
import { RoleSelectionSection } from "@/components/RoleSelectionSection";
import { StudentDashboard } from "@/components/StudentDashboard";
import { InstructorDashboard } from "@/components/InstructorDashboard";
import { AdminDashboard } from "@/components/AdminDashboard";
import {
  Archive,
  ChevronRight,
  GraduationCap,
  Landmark,
  LogOut,
  Shield,
  Terminal,
  UserCog,
} from "lucide-react";
import { ProfileModal } from "@/components/ProfileModal";

const roleStyles: Record<string, string> = {
  admin: "text-[var(--color-error)] bg-red-50 border-red-200",
  instructor: "text-[var(--color-success)] bg-green-50 border-green-200",
  student: "text-[var(--color-accent)] bg-blue-50 border-blue-200",
};

export default function Home() {
  const { user, loading, logout } = useAuth();
  const [profileOpen, setProfileOpen] = React.useState(false);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-paper)] px-6 text-[var(--color-ink)]">
        <div className="w-full max-w-sm border border-[var(--color-rule)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-panel)]">
          <div className="mb-4 flex items-center gap-3">
            <Terminal className="w-5 h-5 text-[var(--color-accent)]" />
            <span className="font-mono text-xs font-bold text-[var(--color-ink-2)]">Opening workspace session</span>
          </div>
          <div className="h-1.5 overflow-hidden bg-[var(--color-paper-2)]">
            <div className="h-full w-2/3 animate-pulse bg-[var(--color-accent)]" />
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[var(--color-paper)] text-[var(--color-ink)]">
        <header className="sticky top-0 z-50 border-b border-[var(--color-rule)] bg-[var(--color-paper)]/95 px-4 py-3 backdrop-blur sm:px-6 lg:px-10">
          <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center border border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)]">
                <Archive className="w-4 h-4" />
              </div>
              <div>
                <span className="block text-sm font-extrabold text-[var(--color-ink)]">GradeWise</span>
                <span className="block text-[10px] font-semibold text-[var(--color-muted)]">Academic grading workbench</span>
              </div>
            </div>
            <span className="hidden border border-[var(--color-rule)] bg-[var(--color-surface)] px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)] sm:inline-flex">
              Secure Google session
            </span>
          </div>
        </header>

        <LandingSection />
      </main>
    );
  }

  const activeRole = user.role;

  if (!activeRole) {
    return (
      <main className="min-h-screen bg-[var(--color-paper)] text-[var(--color-ink)]">
        <RoleSelectionSection />
      </main>
    );
  }

  const getSidebarMeta = (role: string) => {
    switch (role) {
      case "admin":
        return { label: "Admin Suite", icon: <Shield className="w-4 h-4" /> };
      case "instructor":
        return { label: "Faculty Hub", icon: <Landmark className="w-4 h-4" /> };
      default:
        return { label: "Student Desk", icon: <GraduationCap className="w-4 h-4" /> };
    }
  };

  const currentMeta = getSidebarMeta(activeRole);

  return (
    <>
      <div className="flex min-h-screen overflow-hidden bg-[var(--color-paper)] text-[var(--color-ink)]">
        <aside className="hidden w-[264px] shrink-0 select-none flex-col border-r border-[var(--color-rule)] bg-[var(--color-ink)] text-[var(--color-paper)] lg:flex">
          <div className="border-b border-[oklch(96%_0.012_92_/_0.14)] p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center border border-[oklch(96%_0.012_92_/_0.22)] bg-[oklch(24%_0.014_82)]">
                <Archive className="w-4 h-4 text-[var(--color-accent-2)]" />
              </div>
              <div>
                <span className="block text-sm font-extrabold">GradeWise</span>
                <span className="block text-[10px] text-[oklch(78%_0.014_92)]">Workbench</span>
              </div>
            </div>
          </div>

          <nav className="flex-1 p-4">
            <div className="mb-3 text-[10px] font-bold uppercase tracking-[0.14em] text-[oklch(72%_0.018_92)]">
              Console
            </div>
            <div className="space-y-2">
              <div className="flex w-full items-center gap-3 border border-[var(--color-accent-2)] bg-[oklch(30%_0.045_255)] px-3 py-3 text-xs font-bold">
                {currentMeta.icon}
                {currentMeta.label}
              </div>
            </div>
          </nav>

          <div className="space-y-3 border-t border-[oklch(96%_0.012_92_/_0.14)] p-4">
            <button
              onClick={() => setProfileOpen(true)}
              className="flex min-h-0 w-full items-center gap-3 border border-[oklch(96%_0.012_92_/_0.14)] bg-[oklch(24%_0.014_82)] p-2 text-left"
              title="Edit profile"
            >
              {user.photoURL ? (
                <img src={user.photoURL} alt={user.displayName} className="h-9 w-9 object-cover" />
              ) : (
                <div className="flex h-9 w-9 items-center justify-center bg-[var(--color-paper)] text-xs font-extrabold text-[var(--color-ink)]">
                  {user.displayName.substring(0, 1).toUpperCase()}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <span className="block truncate text-xs font-bold">{user.displayName}</span>
                <span className="block truncate font-mono text-[9px] text-[oklch(76%_0.012_92)]">{user.email}</span>
              </div>
              <UserCog className="h-4 w-4 shrink-0 text-[oklch(76%_0.012_92)]" />
            </button>

            <button
              onClick={logout}
              className="flex w-full items-center justify-center gap-2 border border-[oklch(96%_0.012_92_/_0.14)] px-3 py-2.5 text-xs font-bold text-[oklch(86%_0.012_92)] hover:bg-[oklch(24%_0.014_82)]"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex items-center justify-between gap-4 border-b border-[var(--color-rule)] bg-[var(--color-paper)]/95 px-4 py-3 backdrop-blur sm:px-6">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-semibold text-[var(--color-muted)]">
                <span>Workspace</span>
                <ChevronRight className="h-3.5 w-3.5" />
                <span className="truncate text-[var(--color-ink)]">{currentMeta.label}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className={`hidden items-center gap-1.5 border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] sm:inline-flex ${roleStyles[activeRole]}`}>
                {currentMeta.icon}
                {currentMeta.label}
              </span>
              <button
                onClick={() => setProfileOpen(true)}
                className="inline-flex h-11 w-11 items-center justify-center border border-[var(--color-rule)] bg-[var(--color-surface)] text-[var(--color-ink)] lg:hidden"
                title="Profile"
              >
                <UserCog className="h-4 w-4" />
              </button>
            </div>
          </header>

          <div className="flex min-h-0 flex-1 flex-col">
            {activeRole === "student" && <StudentDashboard />}
            {activeRole === "instructor" && <InstructorDashboard />}
            {activeRole === "admin" && <AdminDashboard />}
          </div>
        </div>
      </div>

      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
    </>
  );
}
