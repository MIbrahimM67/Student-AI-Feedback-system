"use client";

import React, { useState, useEffect } from "react";
import api from "@/lib/api";
import { 
  CheckCircle2, AlertTriangle, Lightbulb, FileText, 
  ArrowLeft, Award, Copy, Check, Terminal, BarChart2, 
  Layers, ShieldAlert, Cpu, Loader2
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

export const StudentFeedbackDetails: React.FC<StudentFeedbackDetailsProps> = ({ submissionId, onBack, studentName = "Student" }) => {
  const [activeTab, setActiveTab] = useState<"scorecard" | "audits" | "metadata">("scorecard");
  const [copied, setCopied] = useState<boolean>(false);
  const [report, setReport] = useState<FeedbackReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-4" />
        <p className="text-sm font-bold text-slate-700">Loading AI Feedback Report...</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 min-h-[400px]">
        <AlertTriangle className="w-8 h-8 text-rose-500 mb-4" />
        <p className="text-sm font-bold text-slate-700">{error || "Report not found"}</p>
        <button onClick={onBack} className="mt-4 py-2 px-4 bg-slate-100 rounded-lg text-xs font-bold hover:bg-slate-200">
          Go Back
        </button>
      </div>
    );
  }

  const isPass = report.status?.toLowerCase() === "pass";
  const sourceCodeText = report.extractedText || report.summary || "No source code or document text captured.";
  const codeLines = sourceCodeText.split("\n");

  const handleCopyCode = () => {
    navigator.clipboard.writeText(sourceCodeText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex-1 flex flex-col space-y-6 p-6 animate-fade-in-up">
      
      {/* Workspace Header Toolbar */}
      <div className="flex items-center justify-between pb-4 border-b border-white/5">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 py-2 px-4 rounded-xl bg-slate-900 border border-white/10 hover:border-white/20 text-slate-350 hover:text-white text-xs font-bold active:scale-95 transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          Workspace Dashboard
        </button>

        <div className="flex items-center gap-3">
          {/* Status Capsule */}
          <span className={`py-1 px-3.5 rounded-full border text-[10px] font-black tracking-widest uppercase flex items-center gap-1.5 ${
            isPass 
              ? "text-emerald-400 border-emerald-500/20 bg-emerald-950/20" 
              : "text-rose-400 border-rose-500/20 bg-rose-950/20"
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full bg-current ${isPass ? "animate-pulse" : "animate-ping"}`} />
            Claim: {report.status || "N/A"}
          </span>

          {report.pdfUrl && (
            <a
              href={report.pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 py-2 px-4 rounded-xl bg-indigo-650 hover:bg-indigo-700 text-white font-bold text-xs shadow-md shadow-indigo-600/10 active:scale-95 transition-all"
            >
              <FileText className="w-4 h-4" />
              Export PDF Sheet
            </a>
          )}
        </div>
      </div>

      {/* --- DUAL PANE GRID SYSTEM --- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch flex-1 min-h-[500px]">
        
        {/* LEFT PANE: Premium IDE-Style File / Code Viewer */}
        <div className="lg:col-span-5 dev-card overflow-hidden flex flex-col min-h-[400px]">
          <div className="py-3 px-4 border-b border-white/5 bg-[#070a13] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-indigo-400" />
              <span className="text-[10px] font-bold tracking-wider font-mono text-slate-350 uppercase">
                original_submission.src
              </span>
            </div>
            <button
              onClick={handleCopyCode}
              className="p-1.5 rounded-lg border border-white/10 hover:bg-slate-900 text-slate-400 hover:text-white transition-all"
              title="Copy to clipboard"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>

          <div className="flex-1 p-4 overflow-y-auto max-h-[550px] font-mono text-xs bg-[#03060c] leading-relaxed relative flex select-text">
            <div className="text-right select-none text-slate-650 pr-4 border-r border-white/5 mr-4 sticky left-0 bg-[#03060c] shrink-0 font-mono">
              {codeLines.map((_, i) => <div key={i} className="h-5">{i + 1}</div>)}
            </div>
            <pre className="text-slate-300 overflow-x-auto whitespace-pre-wrap font-mono flex-1 text-left">
              {codeLines.map((line, i) => <div key={i} className="h-5">{line || " "}</div>)}
            </pre>
          </div>
        </div>

        {/* RIGHT PANE: Multi-Agent Interactive Audit Deck */}
        <div className="lg:col-span-7 dev-card flex flex-col overflow-hidden">
          <div className="py-3 px-6 border-b border-white/5 bg-[#070a13] flex items-center gap-4">
            <button
              onClick={() => setActiveTab("scorecard")}
              className={`pb-2.5 pt-1.5 border-b-2 font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer ${
                activeTab === "scorecard" ? "border-indigo-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" /> AI Scorecard
            </button>
            <button
              onClick={() => setActiveTab("audits")}
              className={`pb-2.5 pt-1.5 border-b-2 font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer ${
                activeTab === "audits" ? "border-indigo-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5" /> Agent Critiques
            </button>
            <button
              onClick={() => setActiveTab("metadata")}
              className={`pb-2.5 pt-1.5 border-b-2 font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer ${
                activeTab === "metadata" ? "border-indigo-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Cpu className="w-3.5 h-3.5" /> Metadata Checks
            </button>
          </div>

          <div className="flex-1 p-6 overflow-y-auto max-h-[500px] space-y-6">
            {/* SCORECARD */}
            {activeTab === "scorecard" && (
              <div className="space-y-6 animate-fade-in-up text-left">
                <div className="grid grid-cols-1 md:grid-cols-12 gap-5 items-center bg-[#070a13] p-5 rounded-2xl border border-white/5">
                  <div className="md:col-span-4 flex flex-col items-center">
                    <div className="relative w-28 h-28 flex items-center justify-center rounded-full border border-white/5 shadow-inner">
                      <div className="text-center space-y-0.5">
                        <span className="text-3xl font-black bg-gradient-to-r from-indigo-400 to-emerald-400 bg-clip-text text-transparent font-mono">
                          {report.overallScore}
                        </span>
                        <span className="text-[10px] text-slate-500 font-bold uppercase block">/ 100</span>
                      </div>
                      <div className="absolute inset-2 rounded-full border border-dashed border-indigo-500/20" />
                    </div>
                  </div>
                  <div className="md:col-span-8 space-y-2">
                    <h4 className="text-xs font-bold text-white font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <Award className="w-4 h-4 text-indigo-400" /> Executive Verdict
                    </h4>
                    <p className="text-xs text-slate-400 leading-relaxed font-semibold">{report.summary}</p>
                  </div>
                </div>

                {report.rubricScores && report.rubricScores.length > 0 && (
                  <div className="space-y-4">
                    <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono">Rubric Breakdowns</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {report.rubricScores.map((item, idx) => {
                        const sPercent = (item.score / item.maxScore) * 100;
                        return (
                          <div key={idx} className="p-4 rounded-xl bg-slate-900/40 border border-white/5 space-y-2">
                            <div className="flex items-center justify-between text-xs font-bold">
                              <span className="text-white">{item.criterion}</span>
                              <span className="text-indigo-400 font-mono">{item.score} / {item.maxScore}</span>
                            </div>
                            <div className="w-full bg-[#030712] h-1.5 rounded-full overflow-hidden border border-white/5">
                              <div className="bg-indigo-500 h-full rounded-full transition-all duration-700" style={{ width: `${sPercent}%` }} />
                            </div>
                            <p className="text-[10px] text-slate-400 italic">"{item.justification}"</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* AUDITS */}
            {activeTab === "audits" && (
              <div className="space-y-6 animate-fade-in-up text-left">
                {report.strengths && report.strengths.length > 0 && (
                  <div className="p-5 rounded-2xl bg-emerald-500/5 border border-emerald-500/10 space-y-3">
                    <h4 className="text-xs font-bold text-emerald-400 font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Strengths Identified
                    </h4>
                    <ul className="space-y-2">
                      {report.strengths.map((str, idx) => (
                        <li key={idx} className="text-xs text-slate-350 leading-relaxed flex items-start gap-2 font-medium">
                          <span className="text-emerald-400">•</span>{str}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {report.weaknesses && report.weaknesses.length > 0 && (
                  <div className="p-5 rounded-2xl bg-rose-500/5 border border-rose-500/10 space-y-3">
                    <h4 className="text-xs font-bold text-rose-450 font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-rose-450" /> Critical Diagnostics
                    </h4>
                    <ul className="space-y-2">
                      {report.weaknesses.map((weak, idx) => (
                        <li key={idx} className="text-xs text-slate-350 leading-relaxed flex items-start gap-2 font-medium">
                          <span className="text-rose-450">•</span>{weak}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {report.suggestions && report.suggestions.length > 0 && (
                  <div className="p-5 rounded-2xl bg-amber-500/5 border border-amber-500/10 space-y-3">
                    <h4 className="text-xs font-bold text-amber-400 font-mono uppercase tracking-widest flex items-center gap-1.5">
                      <Lightbulb className="w-4 h-4 text-amber-400" /> Actionable Recommendations
                    </h4>
                    <ul className="space-y-2">
                      {report.suggestions.map((sug, idx) => (
                        <li key={idx} className="text-xs text-slate-350 leading-relaxed flex items-start gap-2 font-medium">
                          <span className="text-amber-400">•</span>{sug}
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
                <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest font-mono">Audit Metadata</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-900/40 border border-white/5 space-y-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono font-bold">Report UID</span>
                    <span className="text-xs font-mono font-bold text-white block truncate">{report.id}</span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900/40 border border-white/5 space-y-1">
                    <span className="text-[9px] text-slate-500 uppercase font-mono font-bold">Submission ID</span>
                    <span className="text-xs font-mono font-bold text-white block truncate">{report.submissionId}</span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900/40 border border-white/5 space-y-1 col-span-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] text-slate-500 uppercase font-mono font-bold">Plagiarism Similarity Index</span>
                      <span className="text-xs font-mono font-bold text-emerald-400">
                        {report.plagiarismPercent !== undefined ? `${report.plagiarismPercent}%` : "0.00% Match"}
                      </span>
                    </div>
                    <div className="w-full bg-[#030712] h-1.5 rounded-full overflow-hidden mt-1.5 border border-white/5">
                      <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${report.plagiarismPercent || 0}%` }} />
                    </div>
                  </div>
                </div>
                <div className="text-[10px] p-4 bg-[#070a13] rounded-xl border border-white/5 leading-relaxed text-slate-450 italic text-center font-mono">
                  🤖 Evaluation audited and consolidated by antigravity multi-agent judicial layers.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
