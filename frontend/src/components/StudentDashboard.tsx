"use client";

import React, { useState, useEffect, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { StudentFeedbackDetails } from "./StudentFeedbackDetails";
import {
  Upload, FileText, Sparkles, BookOpen, Clock, AlertTriangle,
  Code, ShieldCheck, History, RefreshCw, X, ChevronRight,
  CheckCircle2, Loader2,
} from "lucide-react";

interface SubmissionSummary {
  id: string;
  type: string;
  file_name: string | null;
  status: string;
  created_at: string;
  ai_overall_score: number | null;
  ai_max_score: number | null;
  final_status: string | null;
  published_at: string | null;
}

const TYPE_OPTIONS = [
  { value: "text", label: "Typed Text", icon: <FileText className="w-3.5 h-3.5" /> },
  { value: "handwritten", label: "Handwritten Scan", icon: <BookOpen className="w-3.5 h-3.5" /> },
  { value: "coding", label: "Code File", icon: <Code className="w-3.5 h-3.5" /> },
];

const STATUS_BADGE: Record<string, string> = {
  uploaded: "bg-blue-50 text-blue-700 border-blue-200",
  processing: "bg-amber-50 text-amber-700 border-amber-200",
  graded: "bg-purple-50 text-purple-700 border-purple-200",
  published: "bg-green-50 text-green-700 border-green-200",
  failed: "bg-red-50 text-red-700 border-red-200",
};

export const StudentDashboard: React.FC = () => {
  const { user } = useAuth();

  const [type, setType] = useState("text");
  const [questionText, setQuestionText] = useState("");
  const [rubricText, setRubricText] = useState("");
  const [inputText, setInputText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successId, setSuccessId] = useState<string | null>(null);

  const [history, setHistory] = useState<SubmissionSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchHistory = async () => {
    try {
      const res = await api.get("/api/student/submissions");
      setHistory(res.data.submissions || []);
    } catch (err: any) {
      console.error("Failed to load submission history:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [user]);

  // Poll for status updates while any submission is still processing
  useEffect(() => {
    const hasProcessing = history.some((s) => ["uploaded", "processing"].includes(s.status));
    if (hasProcessing) {
      pollRef.current = setInterval(fetchHistory, 5000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [history]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessId(null);
    setUploading(true);
    setStage("Uploading submission...");

    const form = new FormData();
    form.append("type", type);
    if (questionText.trim()) form.append("question_text", questionText);
    if (rubricText.trim()) form.append("rubric_text", rubricText);
    if (inputText.trim()) form.append("input_text", inputText);
    if (file) form.append("file", file);

    try {
      setStage("Sending to grading pipeline...");
      const res = await api.post("/api/student/submissions", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setSuccessId(res.data.submission_id);
      setStage("");
      setQuestionText("");
      setRubricText("");
      setInputText("");
      setFile(null);
      fetchHistory();
    } catch (err: any) {
      setError(err.message || "Submission failed. Please try again.");
      setStage("");
    } finally {
      setUploading(false);
    }
  };

  if (selectedId) {
    return (
      <StudentFeedbackDetails
        submissionId={selectedId}
        onBack={() => { setSelectedId(null); fetchHistory(); }}
      />
    );
  }

  return (
    <div className="flex flex-col lg:flex-row gap-0 flex-1 min-h-0">

      {/* ---- LEFT: Submission Form ---------------------------------------- */}
      <div className="w-full lg:w-[400px] shrink-0 border-r border-[#eae7e1] p-6 overflow-y-auto">
        <div className="mb-6">
          <h2 className="text-base font-bold text-[#1c1c18] font-display">New Submission</h2>
          <p className="text-xs text-[#8e8b80] mt-0.5">Submit your assignment for AI evaluation</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Type selector */}
          <div>
            <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest mb-2 block">
              Submission Type
            </label>
            <div className="grid grid-cols-3 gap-2">
              {TYPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setType(opt.value)}
                  className={`flex flex-col items-center gap-1.5 py-3 px-2 rounded-xl border text-[10px] font-bold transition-all cursor-pointer
                    ${type === opt.value
                      ? "border-[#1c1c18] bg-[#1c1c18] text-white shadow-sm"
                      : "border-[#dfdbd3] bg-white text-[#5e5c54] hover:border-[#1c1c18] hover:text-[#1c1c18]"
                    }`}
                >
                  {opt.icon}
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Ad-hoc Question Input */}
          <div>
            <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest mb-1.5 block">
              Question Prompt
            </label>
            <textarea
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
              rows={3}
              className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] resize-none transition-colors"
              placeholder="Type or paste the assignment question here..."
            />
          </div>

          {/* Ad-hoc Rubric Input */}
          <div>
            <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest mb-1.5 block">
              Grading Rubric (Optional)
            </label>
            <textarea
              value={rubricText}
              onChange={(e) => setRubricText(e.target.value)}
              rows={2}
              className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] resize-none transition-colors"
              placeholder="e.g. Grammar (25%), Content (50%), Formatting (25%)"
            />
          </div>

          {/* Text input */}
          {type !== "handwritten" && (
            <div>
              <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest mb-1.5 block">
                Answer Text {type !== "coding" && "(or upload a file below)"}
              </label>
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                rows={6}
                className="w-full text-xs border border-[#dfdbd3] rounded-xl px-3 py-2.5 bg-white text-[#1c1c18] placeholder-[#8e8b80] focus:outline-none focus:border-[#1c1c18] resize-none transition-colors"
                placeholder={
                  type === "coding"
                    ? "Paste your code here, or upload a file..."
                    : "Type or paste your answer here..."
                }
              />
            </div>
          )}

          {/* File upload */}
          <div>
            <label className="text-[10px] font-bold text-[#5e5c54] uppercase tracking-widest mb-1.5 block">
              Upload File (PDF, DOCX, Image, Code)
            </label>
            <div
              onClick={() => fileRef.current?.click()}
              className={`w-full border-2 border-dashed rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer transition-all
                ${file ? "border-[#1c1c18] bg-[#f5f3ef]" : "border-[#dfdbd3] hover:border-[#1c1c18] bg-white"}`}
            >
              {file ? (
                <>
                  <CheckCircle2 className="w-5 h-5 text-green-600" />
                  <span className="text-xs font-semibold text-[#1c1c18] text-center truncate max-w-full">{file.name}</span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                    className="text-[10px] text-red-500 hover:text-red-700 font-bold"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <>
                  <Upload className="w-5 h-5 text-[#8e8b80]" />
                  <span className="text-xs text-[#8e8b80] text-center">Click to upload (max 5MB)</span>
                </>
              )}
              <input
                ref={fileRef}
                type="file"
                className="hidden"
                accept=".pdf,.docx,.doc,.txt,.py,.java,.cpp,.png,.jpg,.jpeg"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200">
              <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <p className="text-xs text-red-700">{error}</p>
            </div>
          )}

          {successId && (
            <div className="flex items-start gap-2 p-3 rounded-xl bg-green-50 border border-green-200">
              <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-green-700">Submitted successfully!</p>
                <p className="text-[10px] text-green-600 mt-0.5">Grading in progress — check the history panel.</p>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={uploading || (!inputText.trim() && !file)}
            className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-[#1c1c18] text-white font-bold text-xs hover:bg-[#33332f] transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {stage || "Submitting..."}
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Submit for Grading
              </>
            )}
          </button>
        </form>
      </div>

      {/* ---- RIGHT: Submission History ------------------------------------- */}
      <div className="flex-1 p-6 overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-base font-bold text-[#1c1c18] font-display">Submission History</h2>
            <p className="text-xs text-[#8e8b80] mt-0.5">{history.length} total submissions</p>
          </div>
          <button
            onClick={fetchHistory}
            className="flex items-center gap-1.5 text-[10px] font-bold text-[#5e5c54] hover:text-[#1c1c18] border border-[#dfdbd3] py-1.5 px-3 rounded-lg cursor-pointer transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            Refresh
          </button>
        </div>

        {historyLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-xl skeleton-shimmer" />
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-2xl bg-[#f4f2eb] flex items-center justify-center mb-3">
              <History className="w-6 h-6 text-[#8e8b80]" />
            </div>
            <p className="text-sm font-bold text-[#1c1c18]">No submissions yet</p>
            <p className="text-xs text-[#8e8b80] mt-1">Submit your first assignment using the form.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {history.map((sub) => (
              <div
                key={sub.id}
                onClick={() => sub.status === "published" ? setSelectedId(sub.id) : null}
                className={`dev-card p-4 flex items-center gap-4 transition-all
                  ${sub.status === "published" ? "cursor-pointer hover:shadow-md" : "opacity-80"}`}
              >
                <div className="w-9 h-9 rounded-xl bg-[#f4f2eb] flex items-center justify-center shrink-0">
                  {sub.type === "coding" ? (
                    <Code className="w-4 h-4 text-[#5e5c54]" />
                  ) : sub.type === "handwritten" ? (
                    <BookOpen className="w-4 h-4 text-[#5e5c54]" />
                  ) : (
                    <FileText className="w-4 h-4 text-[#5e5c54]" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-[#1c1c18] truncate">
                    {sub.file_name || `${sub.type} submission`}
                  </p>
                  <p className="text-[10px] text-[#8e8b80] mt-0.5 font-mono">
                    {new Date(sub.created_at).toLocaleString()}
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  {sub.ai_overall_score != null && sub.status === "published" && (
                    <span className="text-xs font-bold text-[#1c1c18]">
                      {sub.ai_overall_score}/{sub.ai_max_score}
                    </span>
                  )}
                  <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${STATUS_BADGE[sub.status] || "bg-gray-50 text-gray-600 border-gray-200"}`}>
                    {sub.status === "processing" ? (
                      <span className="flex items-center gap-1">
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                        Grading
                      </span>
                    ) : sub.status}
                  </span>
                  {sub.status === "published" && (
                    <ChevronRight className="w-3.5 h-3.5 text-[#8e8b80]" />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
