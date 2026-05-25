"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { StudentFeedbackDetails } from "./StudentFeedbackDetails";
import { Upload, FileText, Sparkles, BookOpen, Clock, AlertTriangle, Code, ShieldCheck, History, Landmark } from "lucide-react";

interface SubmissionSummary {
  id: string;
  type: string;
  fileName: string;
  prompt: string;
  rubric: string;
  status: string;
  createdAt: string;
  feedbackReportId?: string;
}

export const StudentDashboard: React.FC = () => {
  const { user, isMock, selectRole } = useAuth();
  
  // Staging Form Fields State
  const [type, setType] = useState<string>("text");
  const [prompt, setPrompt] = useState<string>("");
  const [rubric, setRubric] = useState<string>("");
  const [inputText, setInputText] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  
  // UI Loading/Status Indicator States
  const [uploading, setUploading] = useState<boolean>(false);
  const [pipelineStage, setPipelineStage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  
  // Active Submissions list & Selected report details
  const [history, setHistory] = useState<SubmissionSummary[]>([]);
  const [selectedReport, setSelectedReport] = useState<any | null>(null);

  // Fetch student submission logs
  const fetchSubmissionHistory = async () => {
    try {
      if (isMock) {
        setHistory([]);
        return;
      }
      
      const response = await api.get(`/api/student/submissions`);
      setHistory(Array.isArray(response.data) ? response.data : []);
    } catch (err: any) {
      console.error("Failed to fetch live database submissions:", err);
      setError("Unable to connect to grading server. Please ensure backend is running.");
      setHistory([]);
    }
  };

  useEffect(() => {
    fetchSubmissionHistory();
  }, [user, isMock]);

  // Handle drag-and-drop actions
  const [dragActive, setDragActive] = useState<boolean>(false);
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile.size > 1048576) {
        setError("File size exceeds 1MB upload limit.");
        return;
      }
      setFile(droppedFile);
      setError(null);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (selectedFile.size > 1048576) {
        setError("File size exceeds 1MB upload limit.");
        return;
      }
      setFile(selectedFile);
      setError(null);
    }
  };

  // Submit single assignment
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("Please specify the assignment prompt details.");
      return;
    }
    if (!inputText.trim() && !file) {
      setError("Please upload an assignment document or paste submission text.");
      return;
    }

    setUploading(true);
    setError(null);
    setSelectedReport(null);

    // Dynamic Micro-Animation stages trigger
    const stages = [
      "Uploading document & checking credentials...",
      "OCR parsing assignment text and code files...",
      "Running compliance and academic policy checks...",
      "Activating Agent Pipeline: Specialist reviewing rubric...",
      "Activating Agent Pipeline: Judge auditing scorecards...",
      "Activating Agent Pipeline: Senior consolidating evaluation...",
      "Rendering ReportLab feedback sheet & uploading PDF..."
    ];

    let stageIdx = 0;
    setPipelineStage(stages[0]);
    const stageTimer = setInterval(() => {
      if (stageIdx < stages.length - 1) {
        stageIdx++;
        setPipelineStage(stages[stageIdx]);
      }
    }, 1800);

    try {
      const formData = new FormData();
      formData.append("type", type);
      formData.append("prompt", prompt);
      formData.append("rubric", rubric);
      
      if (file) {
        formData.append("file", file);
      } else {
        formData.append("inputText", inputText);
      }

      const response = await api.post("/api/student/submissions", formData, {
        headers: {
          "Content-Type": "multipart/form-data"
        }
      });

      clearInterval(stageTimer);
      
      if (response.data.status === "flagged") {
        setError(`Compliance Check Flagged: ${response.data.reason}`);
        fetchSubmissionHistory();
      } else {
        // Load report directly
        setSelectedReport(response.data.evaluation);
        if (response.data.pdfUrl) {
          setSelectedReport((prev: any) => ({ ...prev, pdfUrl: response.data.pdfUrl }));
        }
        
        // Reset form
        setInputText("");
        setFile(null);
        setPrompt("");
        setRubric("");
        
        fetchSubmissionHistory();
      }

    } catch (err: any) {
      clearInterval(stageTimer);
      setError(err.message || "Failed to submit assignment.");
    } finally {
      setUploading(false);
      setPipelineStage("");
    }
  };

  const handleSelectHistory = async (sub: SubmissionSummary) => {
    if (!sub.feedbackReportId) return;
    setUploading(true);
    setError(null);
    try {
      const response = await api.get(`/api/student/submissions/${sub.id}/feedback`);
      setSelectedReport(response.data);
    } catch (err: any) {
      console.error("Failed to load backend report:", err);
      setError("Failed to retrieve grading report from the live database. Please check your network connection.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-6xl w-full mx-auto px-4 py-8 space-y-10 animate-fade-in-up">
      
      {/* Dynamic Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h2 className="text-3xl font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
            <Sparkles className="w-7 h-7 text-indigo-500 animate-float" />
            Student Submission Console
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Instantly grade coding, scan handwriting OCR, and track historical results.
          </p>
        </div>
      </div>

      {/* Primary Detail Visualizer Override */}
      {selectedReport ? (
        <StudentFeedbackDetails 
          report={selectedReport} 
          onBack={() => setSelectedReport(null)}
          studentName={user?.displayName}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          
          {/* Left Grid Panel: Submission Form */}
          <div className="lg:col-span-7 space-y-6">
            <div className="glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg relative">
              <h3 className="text-lg font-black text-slate-800 dark:text-slate-100 mb-6 flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-indigo-500" />
                Submit New Assignment
              </h3>

              {error && (
                <div className="mb-6 p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-150 dark:border-rose-900/50 text-rose-600 dark:text-rose-450 text-xs font-semibold">
                  {error}
                </div>
              )}

              {uploading ? (
                /* Multi-Agent Loading pipeline tracer */
                <div className="py-16 text-center space-y-6">
                  <div className="relative w-20 h-20 mx-auto">
                    <div className="absolute inset-0 rounded-full border-4 border-slate-100 dark:border-slate-800" />
                    <div className="absolute inset-0 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin" />
                  </div>
                  
                  <div className="space-y-2">
                    <p className="text-slate-800 dark:text-slate-100 font-extrabold text-base">Running AI Evaluation Pipeline</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 font-medium px-4 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800/80 w-fit mx-auto border border-slate-200 dark:border-slate-700 animate-pulse-subtle">
                      {pipelineStage}
                    </p>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5">
                  {/* Row: Assignment Format selector */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-extrabold text-slate-500 uppercase">Assignment Type</label>
                      <select
                        value={type}
                        onChange={(e) => setType(e.target.value)}
                        className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:border-indigo-500 dark:focus:border-indigo-500 text-xs font-semibold focus:outline-none transition-all"
                      >
                        <option value="text">Standard Essay</option>
                        <option value="handwritten">Handwritten scan (OCR)</option>
                        <option value="coding">Programming Code</option>
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-extrabold text-slate-500 uppercase">Target Language/Theme</label>
                      <div className="w-full py-2.5 px-3.5 rounded-xl bg-slate-100 dark:bg-slate-950 border border-slate-150 dark:border-slate-850 text-xs text-slate-500 font-semibold cursor-not-allowed">
                        {type === "coding" ? "C++, Java, or Python" : (type === "handwritten" ? "Image / Scanned PDF" : "Text document")}
                      </div>
                    </div>
                  </div>

                  {/* Form Field: Prompt */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-extrabold text-slate-500 uppercase">Assignment Prompt</label>
                    <textarea
                      placeholder="e.g. Write a python script to sort a list using bubble sort, explaining temporal complexities."
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      rows={3}
                      className="w-full py-3 px-4 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:border-indigo-500 dark:focus:border-indigo-500 text-xs font-medium focus:outline-none transition-all placeholder-slate-400"
                    />
                  </div>

                  {/* Form Field: Rubric */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-extrabold text-slate-500 uppercase">Custom Grading Rubric (Optional)</label>
                    <textarea
                      placeholder="e.g. Clean syntax (30pts), Algorithmic logic (40pts), Temporal complexity explains (30pts)"
                      value={rubric}
                      onChange={(e) => setRubric(e.target.value)}
                      rows={2}
                      className="w-full py-3 px-4 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:border-indigo-500 dark:focus:border-indigo-500 text-xs font-medium focus:outline-none transition-all placeholder-slate-400"
                    />
                  </div>

                  {/* Drag and Drop Upload Area */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-extrabold text-slate-500 uppercase">Submission Content</label>
                    
                    <div
                      onDragEnter={handleDrag}
                      onDragOver={handleDrag}
                      onDragLeave={handleDrag}
                      onDrop={handleDrop}
                      className={`relative border-2 border-dashed rounded-2xl py-8 px-4 text-center transition-all ${
                        dragActive 
                          ? "border-indigo-500 bg-indigo-50/10" 
                          : "border-slate-200 dark:border-slate-800 hover:border-slate-350 hover:bg-slate-50/30 dark:hover:bg-slate-850/20"
                      }`}
                    >
                      <input
                        type="file"
                        id="file-upload"
                        multiple={false}
                        onChange={handleFileChange}
                        className="hidden"
                      />
                      
                      <div className="space-y-3">
                        <div className="mx-auto p-3 bg-slate-100 dark:bg-slate-950/60 rounded-full border border-slate-200 dark:border-slate-800 w-fit text-slate-400">
                          <Upload className="w-5 h-5" />
                        </div>
                        
                        <div className="text-xs">
                          <label htmlFor="file-upload" className="font-extrabold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer">
                            Click to upload file
                          </label>
                          <span className="text-slate-500 font-medium"> or drag and drop here</span>
                        </div>
                        
                        <p className="text-[10px] text-slate-400 font-medium">
                          Supports PDF, DOCX, TXT, PY, CPP, JAVA, PNG, JPG (Max size: 1MB)
                        </p>
                      </div>
                    </div>

                    {file && (
                      <div className="flex items-center gap-2 p-3 bg-indigo-50/20 dark:bg-slate-950/60 border border-indigo-150 dark:border-indigo-900/30 rounded-xl mt-3 animate-pulse-subtle">
                        <FileText className="w-4 h-4 text-indigo-500" />
                        <span className="text-xs font-bold text-slate-700 dark:text-slate-300 truncate max-w-[200px]">{file.name}</span>
                        <span className="text-[10px] text-slate-400">({(file.size / 1024).toFixed(1)} KB)</span>
                        <button
                          type="button"
                          onClick={() => setFile(null)}
                          className="ml-auto text-xs text-rose-500 hover:underline font-bold"
                        >
                          Clear
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Fallback Paste Text Input */}
                  {!file && (
                    <div className="space-y-1.5">
                      <div className="text-center text-[10px] text-slate-400 font-bold uppercase tracking-wider my-3">— OR Paste Text Draft —</div>
                      <textarea
                        placeholder="Paste your assignment essay or program code here..."
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        rows={5}
                        className="w-full py-3 px-4 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:border-indigo-500 dark:focus:border-indigo-500 text-xs font-mono focus:outline-none transition-all placeholder-slate-400"
                      />
                    </div>
                  )}

                  {/* Submit Button */}
                  <button
                    type="submit"
                    className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-lg shadow-indigo-600/25 active:scale-98 transition-all cursor-pointer mt-4"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    Submit to Multi-Agent Evaluator
                  </button>
                </form>
              )}
            </div>
          </div>

          {/* Right Grid Panel: Historical Logs */}
          <div className="lg:col-span-5 space-y-6">
            <div className="glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg relative h-full flex flex-col">
              <h3 className="text-lg font-black text-slate-800 dark:text-slate-100 mb-6 flex items-center gap-2">
                <History className="w-5 h-5 text-indigo-500" />
                Historical Evaluations
              </h3>

              {history.length === 0 ? (
                <div className="flex-1 flex flex-col justify-center items-center py-16 text-slate-400 space-y-2">
                  <Clock className="w-8 h-8 opacity-40 animate-pulse-subtle" />
                  <p className="text-xs font-bold">No historical submissions found.</p>
                  <p className="text-[10px] text-slate-500 text-center">New reports will appear here after grading is complete.</p>
                </div>
              ) : (
                <div className="space-y-4 overflow-y-auto max-h-[500px] pr-1.5 flex-1">
                  {history.map((sub, idx) => {
                    const isCompleted = sub.status === "completed";
                    const statusText = isCompleted ? "Graded" : (sub.status === "failed" ? "Violation" : "Processing");
                    const badgeColor = isCompleted 
                      ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border-emerald-150 dark:border-emerald-900/40"
                      : (sub.status === "failed" ? "bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-450 border-rose-150 dark:border-rose-900/40" : "bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-450 border-amber-150 dark:border-amber-900/40 animate-pulse");

                    return (
                      <div
                        key={idx}
                        onClick={() => handleSelectHistory(sub)}
                        className={`p-4 rounded-2xl border bg-white/50 dark:bg-slate-950/30 hover:-translate-y-0.5 shadow-sm hover:shadow-md cursor-pointer transition-all ${
                          isCompleted 
                            ? "border-slate-200 dark:border-slate-850 hover:border-indigo-400 dark:hover:border-indigo-500"
                            : "border-slate-200 dark:border-slate-850 opacity-80"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className={`py-1 px-2.5 rounded-lg border font-bold text-[9px] uppercase tracking-wider ${badgeColor}`}>
                            {statusText}
                          </span>
                          <span className="text-[10px] text-slate-400 font-medium">
                            {new Date(sub.createdAt).toLocaleDateString()}
                          </span>
                        </div>

                        <div className="space-y-1">
                          <div className="text-xs font-extrabold text-slate-800 dark:text-slate-200 truncate">{sub.fileName}</div>
                          <div className="text-[10px] text-slate-550 dark:text-slate-400 truncate italic">"{sub.prompt}"</div>
                        </div>

                        {isCompleted && (
                          <div className="mt-3 flex items-center justify-end text-[10px] font-bold text-indigo-600 dark:text-indigo-400">
                            View Report →
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

        </div>
        
        {/* Settings Upgrade Card (Strictly visible only to active students) */}
        {user?.role === "student" && (
          <div className="dev-card bg-white p-8 rounded-3xl border border-[#dfdbd3] shadow-sm mt-10">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-2 text-left">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-violet-50 border border-violet-100 text-violet-750 text-[10px] font-bold uppercase tracking-wider">
                  <Sparkles className="w-3.5 h-3.5" />
                  Academic Profile Settings
                </div>
                <h3 className="text-xl font-bold text-[#1c1c18] font-display">Upgrade to GradeWise Faculty Hub</h3>
                <p className="text-xs text-[#5e5c54] font-medium max-w-xl leading-relaxed">
                  Switch your account type to the **Faculty / Instructor Hub** to unlock certified class batch submissions, customizable grading rubrics, plagiarism vector similarity logs, and professional grading PDF downloads.
                </p>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <button
                  onClick={async () => {
                    try {
                      await selectRole("instructor");
                    } catch (err) {
                      console.error("Failed to upgrade role:", err);
                    }
                  }}
                  className="flex items-center gap-2 py-3 px-5 rounded-xl bg-[#1c1c18] hover:bg-[#33332f] text-white font-bold text-xs shadow-md transition-all active:scale-98 cursor-pointer font-sans"
                >
                  <Landmark className="w-4 h-4 text-white" />
                  Apply for Faculty Status & Pro
                </button>
              </div>
            </div>
          </div>
        )}
        </>
      )}

    </div>
  );
};
