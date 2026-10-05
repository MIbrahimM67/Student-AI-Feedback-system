"use client";

import React from "react";
import { useAuth } from "@/context/AuthContext";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  CheckCircle2,
  Code,
  FileText,
  LogIn,
  ScanText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

export const LandingSection: React.FC = () => {
  const { loginWithGoogle, error, loading } = useAuth();
  const documentDemo = process.env.NEXT_PUBLIC_DOCUMENT_DEMO === "true";

  const workflow = [
    { icon: <FileText className="w-4 h-4" />, label: "Submit", text: documentDemo ? "Text, documents, or scans" : "Text, files, scans, or code" },
    { icon: <ScanText className="w-4 h-4" />, label: "Extract", text: "OCR and document parsing" },
    { icon: documentDemo ? <BookOpen className="w-4 h-4" /> : <Code className="w-4 h-4" />, label: documentDemo ? "Grade" : "Run", text: documentDemo ? "Reference and rubric checks" : "Sandboxed code checks" },
    { icon: <ShieldCheck className="w-4 h-4" />, label: "Review", text: "Rubrics, warnings, reports" },
  ];

  const panels = [
    { title: "Student", text: "Submit assignments and open published feedback without navigating a marketing maze." },
    { title: "Instructor", text: "Stage subjects, references, assignments, and batches in one operational workspace." },
    { title: "Admin", text: "Handle faculty verification, warning resolution, and audit logs from a dense registry view." },
  ];

  return (
    <div className="flex-1 px-4 py-8 sm:px-6 lg:px-10">
      <div className="mx-auto grid min-h-[calc(100vh-116px)] w-full max-w-7xl grid-cols-1 gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-stretch">
        <section className="flex flex-col justify-between border border-[var(--color-rule)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-panel)] sm:p-8">
          <div className="space-y-8">
            <div className="inline-flex items-center gap-2 border border-[var(--color-rule)] bg-[var(--color-paper-2)] px-3 py-2 text-xs font-semibold text-[var(--color-ink-2)]">
              <Sparkles className="w-4 h-4 text-[var(--color-accent)]" />
              {documentDemo ? "Document grading demo" : "Academic grading workbench"}
            </div>

            <div className="space-y-5">
              <h1 className="max-w-3xl text-4xl leading-[1.02] tracking-normal text-[var(--color-ink)] sm:text-5xl lg:text-6xl">
                GradeWise
              </h1>
              <p className="max-w-2xl text-base leading-7 text-[var(--color-ink-2)] sm:text-lg">
                {documentDemo
                  ? "Submit documents, process handwritten work, grade against references and rubrics, and publish feedback for students."
                  : "One place to submit assignments, run rubric checks, inspect code execution, process handwritten work, and publish feedback for students."}
              </p>
              {documentDemo && <p className="text-xs leading-5 text-[var(--color-muted)]">Code execution, knowledge-base search, and plagiarism checks are paused in this demo.</p>}
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {workflow.map((item) => (
                <div key={item.label} className="flex min-h-20 items-start gap-3 border border-[var(--color-rule)] bg-[var(--color-paper)] p-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center border border-[var(--color-rule)] bg-[var(--color-surface)] text-[var(--color-accent)]">
                    {item.icon}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-[var(--color-ink)]">{item.label}</p>
                    <p className="mt-1 text-xs leading-5 text-[var(--color-muted)]">{item.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-10 border-t border-[var(--color-rule)] pt-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-5 text-[var(--color-muted)]">
                Google sign-in opens the role-aware workspace for students, faculty, or administrators.
              </p>
              <button
                onClick={loginWithGoogle}
                disabled={loading}
                className="inline-flex shrink-0 items-center justify-center gap-2 border border-[var(--color-ink)] bg-[var(--color-ink)] px-5 py-3 text-sm font-bold text-[var(--color-paper)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <LogIn className="w-4 h-4" />
                {loading ? "Signing in" : "Sign in with Google"}
              </button>
            </div>
            {error && (
              <div className="mt-4 flex items-start gap-2 border border-[var(--color-error)] bg-red-50 p-3 text-xs text-[var(--color-error)]">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                {error}
              </div>
            )}
          </div>
        </section>

        <section className="grid grid-rows-[auto_1fr] gap-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {panels.map((panel) => (
              <div key={panel.title} className="border border-[var(--color-rule)] bg-[var(--color-surface)] p-4">
                <p className="text-sm font-bold text-[var(--color-ink)]">{panel.title}</p>
                <p className="mt-2 text-xs leading-5 text-[var(--color-muted)]">{panel.text}</p>
              </div>
            ))}
          </div>

          <div className="relative overflow-hidden border border-[var(--color-rule)] bg-[var(--color-ink)] p-4 text-[var(--color-paper)] shadow-[var(--shadow-panel)] sm:p-6">
            <div className={`grid h-full min-h-[480px] grid-cols-1 gap-4 ${documentDemo ? "lg:grid-cols-[160px_minmax(0,1fr)]" : "lg:grid-cols-[220px_minmax(0,1fr)]"}`}>
              <div className="space-y-3 border border-[oklch(96%_0.012_92_/_0.16)] bg-[oklch(24%_0.014_82)] p-4">
                <div className="mb-6 flex items-center gap-2 text-xs font-bold">
                  <Archive className="w-4 h-4 text-[var(--color-accent-2)]" />
                  Workspace
                </div>
                {["New submission", "Batch review", "Warnings", "Audit log"].map((item, index) => (
                  <div
                    key={item}
                    className={`border px-3 py-2 text-xs ${
                      index === 0
                        ? "border-[var(--color-accent-2)] bg-[oklch(30%_0.045_255)] text-[var(--color-paper)]"
                        : "border-[oklch(96%_0.012_92_/_0.12)] text-[oklch(86%_0.012_92)]"
                    }`}
                  >
                    {item}
                  </div>
                ))}
              </div>

              <div className="grid grid-rows-[auto_1fr] gap-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {[
                    ["Input", "Question + answer"],
                    ["Checks", documentDemo ? "OCR + rubric" : "OCR + sandbox"],
                    ["Output", "PDF feedback"],
                  ].map(([label, value]) => (
                    <div key={label} className="border border-[oklch(96%_0.012_92_/_0.14)] bg-[oklch(22%_0.014_82)] p-4">
                      <p className="text-[10px] font-bold uppercase text-[oklch(74%_0.02_92)]">{label}</p>
                      <p className="mt-2 text-sm font-bold">{value}</p>
                    </div>
                  ))}
                </div>

                <div className={`grid gap-4 ${documentDemo ? "lg:grid-cols-1" : "lg:grid-cols-[minmax(0,1fr)_280px]"}`}>
                  <div className="border border-[oklch(96%_0.012_92_/_0.14)] bg-[oklch(15%_0.012_82)] p-4 font-mono text-xs">
                    <div className="mb-4 flex items-center justify-between border-b border-[oklch(96%_0.012_92_/_0.12)] pb-3">
                      <span className="text-[oklch(74%_0.02_92)]">{documentDemo ? "submission.txt" : "submission.cpp"}</span>
                      <CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" />
                    </div>
                    {(documentDemo ? [
                      "Question: When does water freeze?",
                      "Answer: At 0°C at standard pressure.",
                      "Reference: Water freezes at 0°C.",
                      "Rubric: State the temperature.",
                    ] : [
                      "01  int main() {",
                      "02    vector<int> scores;",
                      "03    run_hidden_tests();",
                      "04    compare_with_rubric();",
                      "05  }",
                    ]).map((line) => (
                      <p key={line} className="leading-7 text-[oklch(88%_0.01_92)]">{line}</p>
                    ))}
                  </div>

                  <div className="space-y-3 border border-[oklch(96%_0.012_92_/_0.14)] bg-[oklch(22%_0.014_82)] p-4">
                    <div className="flex items-center gap-2 text-sm font-bold">
                      <BookOpen className="w-4 h-4 text-[var(--color-accent-2)]" />
                      Feedback sheet
                    </div>
                    {(documentDemo ? ["Rubric alignment", "Reference evidence", "Instructor review"] : ["Rubric alignment", "Runtime evidence", "Plagiarism signal"]).map((item) => (
                      <div key={item} className="flex items-center justify-between border-b border-[oklch(96%_0.012_92_/_0.1)] py-3 text-xs">
                        <span className="text-[oklch(84%_0.012_92)]">{item}</span>
                        <span className="h-2 w-10 bg-[var(--color-accent-2)]" />
                      </div>
                    ))}
                    <p className="pt-2 text-xs leading-5 text-[oklch(78%_0.014_92)]">
                      Screens stay functional: submit, review, publish. The design stays out of the grading flow.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
