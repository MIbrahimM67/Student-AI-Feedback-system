"use client";

import React, { useState, useEffect } from "react";
import api from "@/lib/api";
import { 
  CheckCircle2, AlertTriangle, Lightbulb, FileText, 
  ArrowLeft, Award, Copy, Check, Terminal, BarChart2, 
  Cpu, Loader2
} from "lucide-react";

interface RubricItem {
  criterion: string;
  score: number;
  maxScore: number;
  justification: string;
}

interface FeedbackReport {
  id: string;
  submissionId: string;
  overallScore: number;
  status: string; // 'pass' | 'fail'
  summary: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  rubricScores: RubricItem[];
  pdfUrl?: string;
  plagiarismPercent?: number;
  extractedText?: string;
}

interface StudentFeedbackDetailsProps {
  submissionId: string;
  onBack: () => void;
  studentName?: string;
}

export const StudentFeedbackDetails: React.FC<StudentFeedbackDetailsProps> = ({ submissionId, onBack }) => {
  const [activeTab, setActiveTab] = useState<"scorecard" | "metadata">("scorecard");
  const [copied, setCopied] = useState<boolean>(false);
  const [report, setReport] = useState<FeedbackReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const res = await api.get(`/api/student/submissions/${submissionId}/pdf`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Feedback_Report_${submissionId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      console.error(err);
      alert(err?.message || "Failed to download PDF report.");
    } finally {
      setDownloadingPdf(false);
    }
  };

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const res = await api.get(`/api/student/submissions/${submissionId}/feedback`);
        setReport(res.data.report || res.data);
      } catch (err: any) {
        setError(err.message || "Failed to load feedback report.");
      } finally {
        setLoading(false);
      }
    };
    fetchReport();
  }, [submissionId]);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 min-h-[400px]">
        <Loader2 className="w-8 h-8 text-[var(--color-accent)] animate-spin mb-4" />
        <p className="text-sm font-bold text-[var(--color-ink)]">Loading feedback report</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 min-h-[400px]">
        <AlertTriangle className="w-8 h-8 text-[var(--color-error)] mb-4" />
        <p className="text-sm font-bold text-[var(--color-ink)]">{error || "Report not found"}</p>
        <button onClick={onBack} className="mt-4 border border-[var(--color-rule)] bg-[var(--color-surface)] px-4 py-2 text-xs font-bold hover:bg-[var(--color-paper-2)]">
          Go Back
        </button>
      </div>
    );
  }

  const isPass = report.status?.toLowerCase() === "pass";
  const needsReview = report.status === "needs_review";
  const sourceCodeText = report.extractedText || report.summary || "No source code or document text captured.";
  const codeLines = sourceCodeText.split("\n");

  const handleCopyCode = () => {
    navigator.clipboard.writeText(sourceCodeText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex-1 flex flex-col space-y-5 p-5 animate-fade-in-up">
      
      {/* Workspace Header Toolbar */}
      <div className="flex flex-col gap-3 border-b border-[var(--color-rule)] pb-4 sm:flex-row sm:items-center sm:justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center justify-center gap-2 border border-[var(--color-rule)] bg-[var(--color-surface)] px-4 py-2 text-xs font-bold text-[var(--color-ink)] transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          Workspace Dashboard
        </button>

        <div className="flex items-center gap-3">
          {/* Status Capsule */}
          <span className={`py-1 px-3.5 rounded-full border text-[10px] font-black tracking-widest uppercase flex items-center gap-1.5 ${
            isPass 
              ? "text-[var(--color-success)] border-green-200 bg-green-50" 
              : needsReview ? "text-amber-700 border-amber-200 bg-amber-50" : "text-[var(--color-error)] border-red-200 bg-red-50"
          }`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            {needsReview ? "AI feedback — review suggested" : `Assessment: ${report.status || "N/A"}`}
          </span>

          <button
            onClick={handleDownloadPdf}
            disabled={downloadingPdf}
            className="inline-flex items-center gap-2 border border-[var(--color-ink)] bg-[var(--color-ink)] px-4 py-2 text-xs font-bold text-[var(--color-paper)] hover:bg-[var(--color-ink-2)] transition-all cursor-pointer disabled:opacity-50"
          >
            {downloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
            {downloadingPdf ? "Generating PDF..." : "Export PDF Sheet"}
          </button>
        </div>
      </div>

      {/* --- DUAL PANE GRID SYSTEM --- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch flex-1 min-h-[500px]">
        
        {/* LEFT PANE: Premium IDE-Style File / Code Viewer */}
        <div className="lg:col-span-5 border border-[var(--color-rule)] bg-[var(--color-ink)] overflow-hidden flex flex-col min-h-[400px]">
          <div className="py-3 px-4 border-b border-[oklch(96%_0.012_92_/_0.14)] bg-[oklch(24%_0.014_82)] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-[var(--color-accent-2)]" />
              <span className="text-[10px] font-bold tracking-wider font-mono text-[oklch(84%_0.012_92)] uppercase">
                original_submission.src
              </span>
            </div>
            <button
              onClick={handleCopyCode}
              className="border border-[oklch(96%_0.012_92_/_0.14)] p-1.5 text-[oklch(84%_0.012_92)] hover:bg-[oklch(30%_0.014_82)] transition-all"
              title="Copy to clipboard"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-[var(--color-success)]" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>

          <div className="flex-1 p-4 overflow-y-auto max-h-[550px] font-mono text-xs bg-[oklch(15%_0.012_82)] leading-relaxed relative flex select-text">
            <div className="text-right select-none text-[oklch(56%_0.014_92)] pr-4 border-r border-[oklch(96%_0.012_92_/_0.1)] mr-4 sticky left-0 bg-[oklch(15%_0.012_82)] shrink-0 font-mono">
              {codeLines.map((_, i) => <div key={i} className="h-5">{i + 1}</div>)}
            </div>
            <pre className="text-[oklch(88%_0.01_92)] overflow-x-auto whitespace-pre-wrap font-mono flex-1 text-left">
              {codeLines.map((line, i) => <div key={i} className="h-5">{line || " "}</div>)}
            </pre>
          </div>
        </div>

        {/* RIGHT PANE: Multi-Agent Interactive Audit Deck */}
        <div className="lg:col-span-7 border border-[var(--color-rule)] bg-[var(--color-surface)] flex flex-col overflow-hidden shadow-[var(--shadow-panel)]">
          <div className="py-3 px-5 border-b border-[var(--color-rule)] bg-[var(--color-paper-2)] flex items-center gap-4">
            <button
              onClick={() => setActiveTab("scorecard")}
              className={`pb-2.5 pt-1.5 border-b-2 font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer ${
                activeTab === "scorecard" ? "border-[var(--color-accent)] text-[var(--color-ink)]" : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-ink)]"
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" /> Full Feedback Report
            </button>
            <button
              onClick={() => setActiveTab("metadata")}
              className={`pb-2.5 pt-1.5 border-b-2 font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer ${
                activeTab === "metadata" ? "border-[var(--color-accent)] text-[var(--color-ink)]" : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-ink)]"
              }`}
            >
              <Cpu className="w-3.5 h-3.5" /> Metadata Checks
            </button>
          </div>

          <div className="flex-1 p-6 overflow-y-auto max-h-[500px] space-y-6">
            {/* SCORECARD */}
            {activeTab === "scorecard" && (
              <div className="space-y-6 animate-fade-in-up text-left">
                <div className="grid grid-cols-1 md:grid-cols-12 gap-5 items-center bg-[var(--color-paper)] p-5 border border-[var(--color-rule)]">
                  <div className="md:col-span-4 flex flex-col items-center">
                    <div className="relative w-28 h-28 flex items-center justify-center rounded-full border border-white/5 shadow-inner">
                      <div className="text-center space-y-0.5">
                        <span className="text-3xl font-black text-[var(--color-ink)] font-mono">
                          {report.overallScore}
                        </span>
                        <span className="text-[10px] text-[var(--color-muted)] font-bold uppercase block">/ 100</span>
                      </div>
                      <div className="absolute inset-2 rounded-full border border-dashed border-[var(--color-rule-2)]" />
                    </div>
                  </div>
                  <div className="md:col-span-8 space-y-2">
                    <h4 className="text-xs font-bold text-[var(--color-ink)] font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <Award className="w-4 h-4 text-[var(--color-accent)]" /> Grading verdict
                    </h4>
                    <p className="text-sm text-[var(--color-ink-2)] leading-relaxed">{report.summary}</p>
                  </div>
                </div>

                {report.rubricScores && report.rubricScores.length > 0 && (
                  <div className="space-y-4">
                    <h4 className="text-[10px] font-bold text-[var(--color-muted)] uppercase tracking-widest font-mono">Rubric breakdowns</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {report.rubricScores.map((item, idx) => {
                        const sPercent = (item.score / item.maxScore) * 100;
                        return (
                          <div key={idx} className="p-4 bg-[var(--color-paper)] border border-[var(--color-rule)] space-y-2">
                            <div className="flex items-center justify-between text-xs font-bold">
                              <span className="text-[var(--color-ink)]">{item.criterion}</span>
                              <span className="text-[var(--color-accent)] font-mono">{item.score} / {item.maxScore}</span>
                            </div>
                            <div className="w-full bg-[var(--color-paper-2)] h-1.5 overflow-hidden border border-[var(--color-rule)]">
                              <div className="bg-[var(--color-accent)] h-full transition-all duration-700" style={{ width: `${sPercent}%` }} />
                            </div>
                            <p className="text-xs text-[var(--color-muted)] italic">{item.justification}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {/* Strengths, weaknesses, and suggestions */}
                {report.strengths && report.strengths.length > 0 && (
                  <div className="p-5 bg-green-50 border border-green-200 space-y-3 mt-8">
                    <h4 className="text-xs font-bold text-[var(--color-success)] font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4" /> Strengths identified
                    </h4>
                    <ul className="space-y-2">
                      {report.strengths.map((str, idx) => (
                        <li key={idx} className="text-xs text-[var(--color-ink-2)] leading-relaxed flex items-start gap-2 font-medium">
                          <span className="text-[var(--color-success)]">-</span>{str}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {report.weaknesses && report.weaknesses.length > 0 && (
                  <div className="p-5 bg-red-50 border border-red-200 space-y-3 mt-4">
                    <h4 className="text-xs font-bold text-[var(--color-error)] font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4" /> Critical diagnostics
                    </h4>
                    <ul className="space-y-2">
                      {report.weaknesses.map((weak, idx) => (
                        <li key={idx} className="text-xs text-[var(--color-ink-2)] leading-relaxed flex items-start gap-2 font-medium">
                          <span className="text-[var(--color-error)]">-</span>{weak}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {report.suggestions && report.suggestions.length > 0 && (
                  <div className="p-5 bg-amber-50 border border-amber-200 space-y-3 mt-4">
                    <h4 className="text-xs font-bold text-[var(--color-warning)] font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <Lightbulb className="w-4 h-4" /> Actionable recommendations
                    </h4>
                    <ul className="space-y-2">
                      {report.suggestions.map((sug, idx) => (
                        <li key={idx} className="text-xs text-[var(--color-ink-2)] leading-relaxed flex items-start gap-2 font-medium">
                          <span className="text-[var(--color-warning)]">-</span>{sug}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* METADATA */}
            {activeTab === "metadata" && (
              <div className="space-y-4 animate-fade-in-up text-left">
                <h4 className="text-[10px] font-bold text-[var(--color-muted)] uppercase tracking-widest font-mono">Audit metadata</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-[var(--color-paper)] border border-[var(--color-rule)] space-y-1">
                    <span className="text-[9px] text-[var(--color-muted)] uppercase font-mono font-bold">Report UID</span>
                    <span className="text-xs font-mono font-bold text-[var(--color-ink)] block truncate">{report.id}</span>
                  </div>
                  <div className="p-4 bg-[var(--color-paper)] border border-[var(--color-rule)] space-y-1">
                    <span className="text-[9px] text-[var(--color-muted)] uppercase font-mono font-bold">Submission ID</span>
                    <span className="text-xs font-mono font-bold text-[var(--color-ink)] block truncate">{report.submissionId}</span>
                  </div>
                  <div className="p-4 bg-[var(--color-paper)] border border-[var(--color-rule)] space-y-1 col-span-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] text-[var(--color-muted)] uppercase font-mono font-bold">Plagiarism similarity index</span>
                      <span className="text-xs font-mono font-bold text-[var(--color-success)]">
                        {report.plagiarismPercent !== undefined ? `${report.plagiarismPercent}%` : "0.00% Match"}
                      </span>
                    </div>
                    <div className="w-full bg-[var(--color-paper-2)] h-1.5 overflow-hidden mt-1.5 border border-[var(--color-rule)]">
                      <div className="bg-[var(--color-success)] h-full" style={{ width: `${report.plagiarismPercent || 0}%` }} />
                    </div>
                  </div>
                </div>
                <div className="text-[10px] p-4 bg-[var(--color-paper)] border border-[var(--color-rule)] leading-relaxed text-[var(--color-muted)] text-center font-mono">
                  Evaluation consolidated from the grading pipeline and stored for audit review.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

