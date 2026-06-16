"use client";

import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Building2,
  GraduationCap,
  Landmark,
  Loader2,
  User,
} from "lucide-react";

export const RoleSelectionSection: React.FC = () => {
  const { user: authUser, selectRole, loading, error } = useAuth();
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedRole, setSelectedRole] = useState<"student" | "instructor" | null>(null);
  const [formData, setFormData] = useState({
    displayName: authUser?.displayName || "",
    institution: "",
    department: "",
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedRole) selectRole(selectedRole, formData);
  };

  const roleCards = [
    {
      role: "student" as const,
      icon: <GraduationCap className="w-5 h-5" />,
      title: "Student",
      text: "Submit work, track progress, and read published feedback.",
    },
    {
      role: "instructor" as const,
      icon: <Landmark className="w-5 h-5" />,
      title: "Instructor",
      text: "Manage subjects, references, assignments, and batch grading.",
    },
  ];

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <div className="grid w-full max-w-5xl grid-cols-1 border border-[var(--color-rule)] bg-[var(--color-surface)] shadow-[var(--shadow-panel)] lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--color-rule)] bg-[var(--color-ink)] p-6 text-[var(--color-paper)] lg:border-b-0 lg:border-r lg:border-[oklch(96%_0.012_92_/_0.14)]">
          <div className="flex h-full flex-col justify-between gap-10">
            <div className="space-y-5">
              <div className="flex h-10 w-10 items-center justify-center border border-[oklch(96%_0.012_92_/_0.22)] bg-[oklch(24%_0.014_82)] font-mono text-sm font-black">
                G
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-[oklch(78%_0.014_92)]">
                  Setup
                </p>
                <h1 className="mt-3 text-3xl leading-tight text-[var(--color-paper)]">
                  Choose the desk you work from.
                </h1>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[1, 2].map((item) => (
                <div
                  key={item}
                  className={`h-1.5 ${step >= item ? "bg-[var(--color-accent-2)]" : "bg-[oklch(96%_0.012_92_/_0.16)]"}`}
                />
              ))}
            </div>
          </div>
        </aside>

        <section className="p-5 sm:p-8">
          <div className="mb-8">
            <h2 className="text-xl font-bold text-[var(--color-ink)]">
              {step === 1 ? "Select role" : "Complete profile"}
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--color-muted)]">
              {step === 1
                ? "This decides which workspace opens after sign-in."
                : "These fields personalize the grading workspace and faculty records."}
            </p>
          </div>

          {step === 1 && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {roleCards.map((card) => {
                  const isSelected = selectedRole === card.role;
                  return (
                    <button
                      key={card.role}
                      onClick={() => setSelectedRole(card.role)}
                      className={`flex min-h-[164px] flex-col items-start justify-between border p-5 text-left ${
                        isSelected
                          ? "border-[var(--color-accent)] bg-[oklch(94%_0.035_255)]"
                          : "border-[var(--color-rule)] bg-[var(--color-paper)] hover:bg-[var(--color-paper-2)]"
                      }`}
                    >
                      <div className="flex h-10 w-10 items-center justify-center border border-[var(--color-rule)] bg-[var(--color-surface)] text-[var(--color-accent)]">
                        {card.icon}
                      </div>
                      <div>
                        <p className="text-base font-bold text-[var(--color-ink)]">{card.title}</p>
                        <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">{card.text}</p>
                      </div>
                    </button>
                  );
                })}
              </div>

              <button
                onClick={() => selectedRole && setStep(2)}
                disabled={!selectedRole}
                className="inline-flex w-full items-center justify-center gap-2 border border-[var(--color-ink)] bg-[var(--color-ink)] px-5 py-3 text-sm font-bold text-[var(--color-paper)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Continue
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {step === 2 && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2 sm:col-span-2">
                  <label className="flex items-center gap-2 text-xs font-bold text-[var(--color-ink)]">
                    <User className="w-3.5 h-3.5 text-[var(--color-muted)]" />
                    Full name
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.displayName}
                    onChange={(e) => setFormData({ ...formData, displayName: e.target.value })}
                    className="w-full border border-[var(--color-rule)] bg-[var(--color-paper)] px-3.5 py-3 text-sm text-[var(--color-ink)]"
                    placeholder="Ayesha Khan"
                  />
                </div>

                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-xs font-bold text-[var(--color-ink)]">
                    <Building2 className="w-3.5 h-3.5 text-[var(--color-muted)]" />
                    Institution
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.institution}
                    onChange={(e) => setFormData({ ...formData, institution: e.target.value })}
                    className="w-full border border-[var(--color-rule)] bg-[var(--color-paper)] px-3.5 py-3 text-sm text-[var(--color-ink)]"
                    placeholder="University / school"
                  />
                </div>

                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-xs font-bold text-[var(--color-ink)]">
                    <BookOpen className="w-3.5 h-3.5 text-[var(--color-muted)]" />
                    Department
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.department}
                    onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                    className="w-full border border-[var(--color-rule)] bg-[var(--color-paper)] px-3.5 py-3 text-sm text-[var(--color-ink)]"
                    placeholder="Computer Science"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-[var(--color-rule)] pt-5 sm:flex-row">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  disabled={loading}
                  className="inline-flex flex-1 items-center justify-center gap-2 border border-[var(--color-rule)] bg-[var(--color-surface)] px-5 py-3 text-sm font-bold text-[var(--color-ink)] disabled:opacity-50"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading || !formData.displayName || !formData.institution || !formData.department}
                  className="inline-flex flex-1 items-center justify-center gap-2 border border-[var(--color-ink)] bg-[var(--color-ink)] px-5 py-3 text-sm font-bold text-[var(--color-paper)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Saving
                    </>
                  ) : (
                    "Complete setup"
                  )}
                </button>
              </div>
            </form>
          )}

          {error && (
            <div className="mt-5 flex items-start gap-2 border border-[var(--color-error)] bg-red-50 p-3 text-xs text-[var(--color-error)]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
