"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { 
  FileSpreadsheet, FileArchive, Upload, Table as TableIcon, 
  Sparkles, CheckCircle2, ShieldAlert, BadgeCheck, Users, 
  Loader2, Play, Plus, RefreshCw, ClipboardList
} from "lucide-react";

interface StagedStudent {
  submissionId: string;
  fileName: string;
  extractedName: string;
}

export const InstructorDashboard: React.FC = () => {
  const { user } = useAuth();
  
  // Faculty Verification Form State
  const [fullName, setFullName] = useState<string>("");
  const [university, setUniversity] = useState<string>("");
  const [department, setDepartment] = useState<string>("");
  const [designation, setDesignation] = useState<string>("");
  const [officialEmail, setOfficialEmail] = useState<string>("");
  const [proofFile, setProofFile] = useState<File | null>(null);
  
  // Staging Batch Upload Field States
  const [prompt, setPrompt] = useState<string>("");
  const [rubric, setRubric] = useState<string>("");
  const [plagEnabled, setPlagEnabled] = useState<boolean>(true);
  const [batchType, setBatchType] = useState<string>("text");
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [stdinText, setStdinText] = useState<string>("");
  
  // Staged student names grid states
  const [batchId, setBatchId] = useState<string | null>(null);
  const [stagedStudents, setStagedStudents] = useState<StagedStudent[]>([]);
  
  // Real-time progress trackers
  const [gradingProgress, setGradingProgress] = useState<{
    status: string;
    totalFiles: number;
    processedFiles: number;
    exportExcelUrl?: string;
    exportZipUrl?: string;
  } | null>(null);

  // General Status Flags
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Polling intervals reference
  const [pollIntervalId, setPollIntervalId] = useState<NodeJS.Timeout | null>(null);

  const isVerified = user?.facultyStatus === "approved";
  const isPending = user?.facultyStatus === "pending";

  useEffect(() => {
    return () => {
      if (pollIntervalId) clearInterval(pollIntervalId);
    };
  }, [pollIntervalId]);

  // Submit faculty upgrade application
  const handleApplyVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName || !university || !officialEmail || !proofFile) {
      setError("Please fill out all mandatory fields and upload a faculty proof.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("fullName", fullName);
      formData.append("university", university);
      formData.append("department", department);
      formData.append("designation", designation);
      formData.append("officialEmail", officialEmail);
      formData.append("proofFile", proofFile);

      await api.post("/api/instructor/faculty-application", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });

      setSuccessMsg("Verification application submitted successfully. Pending administrative approval.");
    } catch (err: any) {
      setError(err.message || "Failed to submit verification request.");
    } finally {
      setLoading(false);
    }
  };

  // Stage batch file uploads
  const handleBatchFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      if (selectedFiles.length + batchFiles.length > 30) {
        setError("Instructor batch uploads are strictly capped at 30 files.");
        return;
      }
      setBatchFiles(prev => [...prev, ...selectedFiles]);
      setError(null);
    }
  };

  const handleStageBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("Please specify the shared assignment prompt.");
      return;
    }
    if (batchFiles.length === 0) {
      setError("Please upload at least one student submission file.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("rubric", rubric);
      formData.append("plagiarismEnabled", String(plagEnabled));
      formData.append("type", batchType);
      if (stdinText.trim()) formData.append("stdin_text", stdinText);
      
      batchFiles.forEach(file => {
        formData.append("files", file);
      });

      const response = await api.post("/api/instructor/batch", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });

      setBatchId(response.data.batchId);
      
      // Auto-extracted name lists mapping
      const nameReviewList = response.data.nameReviewList.map((item: any) => ({
        submissionId: item.submissionId,
        fileName: item.fileName,
        extractedName: item.extractedName || "Unknown Student"
      }));
      setStagedStudents(nameReviewList);
      
    } catch (err: any) {
      setError(err.message || "Failed to initialize batch uploads.");
    } finally {
      setLoading(false);
    }
  };

  // Edit student name in-place in local table
  const handleEditName = (index: number, newName: string) => {
    setStagedStudents(prev => {
      const copy = [...prev];
      copy[index].extractedName = newName;
      return copy;
    });
  };

  // Confirm Names and launch background bulk grading
  const handleConfirmAndProcess = async () => {
    if (!batchId) return;
    setLoading(true);
    setError(null);
    try {
      // 1. Save refined student names mapping
      const namesMapping = stagedStudents.map(s => ({
        submissionId: s.submissionId,
        studentName: s.extractedName
      }));
      
      await api.post(`/api/instructor/batch/${batchId}/confirm-names`, {
        names: namesMapping
      });

      // 2. Trigger asynchronous background bulk processing
      const processRes = await api.post(`/api/instructor/batch/${batchId}/process`);
      
      setSuccessMsg("Bulk grading started! Tracking progress below.");
      setGradingProgress({
        status: "processing",
        totalFiles: stagedStudents.length,
        processedFiles: 0
      });

      // Clear reviews
      setStagedStudents([]);
      setBatchFiles([]);

      // Start Polling real-time background indicators
      startPollingProgress(batchId);

    } catch (err: any) {
      setError(err.message || "Failed to process batch grading.");
    } finally {
      setLoading(false);
    }
  };

  const startPollingProgress = (id: string) => {
    if (pollIntervalId) clearInterval(pollIntervalId);

    const interval = setInterval(async () => {
      try {
        const response = await api.get(`/api/instructor/batch/${id}`);
        const data = response.data;
        
        setGradingProgress({
          status: data.status,
          totalFiles: data.totalFiles,
          processedFiles: data.processedFiles,
          exportExcelUrl: data.exportExcelUrl,
          exportZipUrl: data.exportZipUrl
        });

        if (data.status === "completed" || data.status === "failed") {
          clearInterval(interval);
          setPollIntervalId(null);
          if (data.status === "completed") {
            setSuccessMsg("Batch grading completed! Aggregated reports are available for download.");
          } else {
            setError("Batch processing failed. Please verify files or contact admin.");
          }
        }
      } catch (err: any) {
        console.error("Backend grading feedback tracking connection lost: ", err);
        setError("Connection lost with backend grading engine. Retrying to reconnect...");
      }
    }, 2500);

    setPollIntervalId(interval);
  };

  return (
    <div className="max-w-6xl w-full mx-auto px-4 py-8 space-y-10 animate-fade-in-up">
      
      {/* Upper Title Row */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h2 className="text-3xl font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
            <BadgeCheck className="w-7 h-7 text-emerald-500 animate-float" />
            Instructor Dashboard
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Conduct multi-agent bulk evaluations, execute similarity checkers, and export grades.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-150 dark:border-rose-900/50 text-rose-600 dark:text-rose-450 text-xs font-semibold">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-150 dark:border-emerald-900/50 text-emerald-600 dark:text-emerald-400 text-xs font-semibold">
          {successMsg}
        </div>
      )}

      {/* PORTAL GATING 1: Non-verified user view Application form */}
      {!isVerified ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Verification application form */}
          <div className="lg:col-span-7 glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-xl space-y-6">
            <div className="space-y-1">
              <h3 className="text-xl font-black text-slate-850 dark:text-slate-100">Faculty Verification Application</h3>
              <p className="text-xs text-slate-500">Provide credentials to unlock batch operations and pro features.</p>
            </div>

            {isPending ? (
              <div className="py-10 text-center space-y-4">
                <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mx-auto" />
                <p className="text-sm font-bold text-slate-700 dark:text-slate-350">Application Pending Review</p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">
                  Your verification details have been recorded. System administrators are reviewing your proof sheets.
                </p>
              </div>
            ) : (
              <form onSubmit={handleApplyVerification} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">Full Name</label>
                    <input
                      type="text"
                      placeholder="Dr. Sarah Jenkins"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">Official Institution Email</label>
                    <input
                      type="email"
                      placeholder="jenkins@qau.edu.pk"
                      value={officialEmail}
                      onChange={(e) => setOfficialEmail(e.target.value)}
                      className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-1.5 col-span-2">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">University / Board</label>
                    <input
                      type="text"
                      placeholder="Quaid-e-Azam University Islamabad"
                      value={university}
                      onChange={(e) => setUniversity(e.target.value)}
                      className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">Department</label>
                    <input
                      type="text"
                      placeholder="Computer Science"
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                      className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] font-extrabold text-slate-500 uppercase">Faculty Designation</label>
                  <input
                    type="text"
                    placeholder="Assistant Professor / Lecturer / Head of Evaluation"
                    value={designation}
                    onChange={(e) => setDesignation(e.target.value)}
                    className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                  />
                </div>

                {/* Proof PDF file input */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-extrabold text-slate-500 uppercase">Employment Proof (PDF / Card)</label>
                  <input
                    type="file"
                    accept="application/pdf,image/*"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setProofFile(e.target.files[0]);
                      }
                    }}
                    className="w-full py-2 px-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-250 dark:border-slate-850 text-xs text-slate-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs active:scale-98 shadow-lg shadow-indigo-600/20 transition-all cursor-pointer disabled:opacity-50"
                >
                  {loading ? "Submitting Request..." : "Submit Verification Papers"}
                </button>
              </form>
            )}
          </div>

          {/* Upgrade Premium Pro Card */}
          <div className="lg:col-span-5 glass-panel bg-gradient-to-br from-indigo-950 via-slate-900 to-indigo-950 text-white p-8 rounded-3xl shadow-2xl relative overflow-hidden space-y-6">
            <div className="absolute top-0 right-0 w-44 h-44 bg-emerald-500/10 rounded-full blur-2xl -z-10" />
            
            <div className="space-y-2">
              <span className="py-1 px-3.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 text-[10px] font-extrabold uppercase tracking-widest">
                Faculty Tier
              </span>
              <h3 className="text-2xl font-black tracking-tight">Assignment Feedback Pro</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Scale your evaluations across whole classrooms instantly. Standard accounts are limited to single-file submissions.
              </p>
            </div>

            <div className="border-t border-slate-800 my-4" />

            <div className="space-y-4">
              <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">Unlocked Pro Privileges:</h4>
              <ul className="space-y-3.5 text-xs text-slate-350">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Staged Bulk Uploads (up to 30 files / 100MB)
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Cross-submission Plagiarism matching comparisons
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Excel summaries export (`openpyxl` aggregates)
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Individual PDF bulk reports compilation (`ZIP` package)
                </li>
              </ul>
            </div>

            <div className="text-xs bg-slate-800/50 p-4 rounded-2xl border border-slate-700/40 text-center leading-relaxed">
              🎓 **Academic Grant Program:** Fully sponsored for public university professors. Simply submit your proof to activate your license.
            </div>
          </div>

        </div>
      ) : (
        /* PORTAL GATING 2: Verified Premium instructor view */
        <div className="space-y-8 animate-fade-in-up">
          
          {/* Active Progress indicators */}
          {gradingProgress && (
            <div className="glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-black text-slate-800 dark:text-slate-100 flex items-center gap-2">
                    <RefreshCw className={`w-5 h-5 text-indigo-500 ${gradingProgress.status === "processing" ? "animate-spin" : ""}`} />
                    Classroom Grading Progress
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">Sequential agent synthesis pipeline executing in backend.</p>
                </div>
                
                <span className="py-1 px-3 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-150 dark:border-indigo-900/40 font-bold text-xs capitalize">
                  Status: {gradingProgress.status}
                </span>
              </div>

              {/* Progress Bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>Processed: {gradingProgress.processedFiles} of {gradingProgress.totalFiles} submissions</span>
                  <span>{Math.round((gradingProgress.processedFiles / gradingProgress.totalFiles) * 100)}%</span>
                </div>
                <div className="w-full bg-slate-100 dark:bg-slate-850 h-3.5 rounded-full overflow-hidden border border-slate-200 dark:border-slate-800">
                  <div 
                    className="bg-gradient-to-r from-indigo-600 to-emerald-500 h-full rounded-full transition-all duration-500"
                    style={{ width: `${(gradingProgress.processedFiles / gradingProgress.totalFiles) * 100}%` }}
                  />
                </div>
              </div>

              {/* Export Aggregates URLs */}
              {gradingProgress.status === "completed" && (
                <div className="flex flex-col md:flex-row items-center gap-4 pt-4 border-t border-slate-200 dark:border-slate-850">
                  {gradingProgress.exportExcelUrl && (
                    <a
                      href={gradingProgress.exportExcelUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full md:w-auto inline-flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-md shadow-emerald-600/10 active:scale-95 transition-all"
                    >
                      <FileSpreadsheet className="w-4.5 h-4.5" />
                      Export Excel Gradesheet
                    </a>
                  )}

                  {gradingProgress.exportZipUrl && (
                    <a
                      href={gradingProgress.exportZipUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full md:w-auto inline-flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-md shadow-indigo-600/10 active:scale-95 transition-all"
                    >
                      <FileArchive className="w-4.5 h-4.5" />
                      Download All PDFs (ZIP Archive)
                    </a>
                  )}

                  <button
                    onClick={() => setGradingProgress(null)}
                    className="w-full md:w-auto ml-auto inline-flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-500 text-xs font-bold hover:bg-slate-50 active:scale-95 transition-all"
                  >
                    Clear Indicators
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Student Names Review Staging grid */}
          {stagedStudents.length > 0 && (
            <div className="glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg space-y-6">
              <div>
                <h3 className="text-lg font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
                  <TableIcon className="w-5 h-5 text-indigo-500" />
                  Confirm Extracted Student Names
                </h3>
                <p className="text-xs text-slate-500 mt-1">Review and refine auto-extracted names before running the multi-agent grading evaluation.</p>
              </div>

              {/* Editable Staging Table Grid */}
              <div className="overflow-x-auto border border-slate-200 dark:border-slate-800 rounded-2xl">
                <table className="w-full border-collapse text-left text-xs">
                  <thead>
                    <tr className="bg-slate-50 dark:bg-slate-950 font-extrabold text-slate-500 border-b border-slate-200 dark:border-slate-800">
                      <th className="py-3 px-4">Filename</th>
                      <th className="py-3 px-4">Assigned Submission ID</th>
                      <th className="py-3 px-4">Student Name (Double click to edit)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {stagedStudents.map((student, index) => (
                      <tr key={index} className="hover:bg-slate-50/40 dark:hover:bg-slate-900/20 font-medium">
                        <td className="py-3.5 px-4 font-mono font-bold text-slate-600 dark:text-slate-350">{student.fileName}</td>
                        <td className="py-3.5 px-4 text-slate-450">{student.submissionId}</td>
                        <td className="py-2.5 px-4">
                          <input
                            type="text"
                            value={student.extractedName}
                            onChange={(e) => handleEditName(index, e.target.value)}
                            className="py-1.5 px-3 rounded-lg bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 font-bold focus:outline-none focus:border-indigo-500 text-xs w-full max-w-[300px]"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center gap-4 justify-end pt-4">
                <button
                  onClick={() => setStagedStudents([])}
                  className="py-2.5 px-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-500 text-xs font-bold hover:bg-slate-50 active:scale-95 transition-all"
                >
                  Cancel Batch
                </button>
                <button
                  onClick={handleConfirmAndProcess}
                  className="inline-flex items-center gap-2 py-2.5 px-5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-md shadow-indigo-600/10 active:scale-95 transition-all"
                >
                  <Play className="w-4 h-4" />
                  Confirm & Run Bulk AI Grader
                </button>
              </div>
            </div>
          )}

          {/* Core Batch Upload Form */}
          {stagedStudents.length === 0 && (
            <div className="max-w-3xl mx-auto glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg space-y-6">
              <h3 className="text-lg font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
                <ClipboardList className="w-5 h-5 text-emerald-500" />
                Upload New Classroom Batch
              </h3>

              {loading ? (
                <div className="py-16 text-center space-y-6">
                  <Loader2 className="w-10 h-10 text-indigo-500 animate-spin mx-auto" />
                  <div className="space-y-1">
                    <p className="text-slate-800 dark:text-slate-100 font-extrabold text-base">Staging Classroom Batch files</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Auto-extracting student names using fast classification models...</p>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleStageBatch} className="space-y-5">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-extrabold text-slate-500 uppercase">Assignments Format</label>
                      <select
                        value={batchType}
                        onChange={(e) => setBatchType(e.target.value)}
                        className="w-full py-2.5 px-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-semibold focus:outline-none"
                      >
                        <option value="text">Standard Text / PDFs</option>
                        <option value="handwritten">Handwritten Scans (OCR)</option>
                        <option value="coding">Programming Code</option>
                      </select>
                    </div>

                    {/* Plagiarism check toggler */}
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-extrabold text-slate-500 uppercase">Plagiarism Scan</label>
                      <div className="flex items-center gap-4.5 p-2.5 bg-white dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 justify-between">
                        <span className="text-xs font-semibold text-slate-650 dark:text-slate-350">Cosine Similarity cross-checks</span>
                        <input
                          type="checkbox"
                          checked={plagEnabled}
                          onChange={(e) => setPlagEnabled(e.target.checked)}
                          className="w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500 cursor-pointer"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Form Field: Prompt */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">Shared Assignment Prompt</label>
                    <textarea
                      placeholder="e.g. Write a program implementing an SLR parser algorithm for MiniLang, demonstrating shift actions."
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      rows={3}
                      className="w-full py-3 px-4 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:outline-none focus:border-indigo-500 text-xs font-medium placeholder-slate-400"
                    />
                  </div>

                  {/* Form Field: Rubric */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">Shared Rubric Parameters (Optional)</label>
                    <textarea
                      placeholder="e.g. Code syntax lints (25%), SLR shifting tables (50%), Edge case handling (25%)"
                      value={rubric}
                      onChange={(e) => setRubric(e.target.value)}
                      rows={2}
                      className="w-full py-3 px-4 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:outline-none focus:border-indigo-500 text-xs font-medium placeholder-slate-400"
                    />
                  </div>

                  {/* Form Field: STDIN (Coding Only) */}
                  {batchType === "coding" && (
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-extrabold text-slate-500 uppercase flex items-center gap-1.5">
                        Input Hints / Data Type <span className="text-slate-400 font-medium normal-case">- Optional</span>
                      </label>
                      <textarea
                        value={stdinText}
                        onChange={(e) => setStdinText(e.target.value)}
                        rows={2}
                        className="w-full py-3 px-4 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 focus:outline-none focus:border-indigo-500 text-xs font-medium placeholder-slate-400"
                        placeholder="e.g. 'numeric array', 'strings', or leave blank to let AI decide..."
                      />
                    </div>
                  )}

                  {/* Multi File drag & drop box */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-extrabold text-slate-500 uppercase">Staged Batch Files (Max: 30 / 100MB)</label>
                    
                    <div className="relative border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-2xl py-8 px-4 text-center hover:border-slate-350 dark:hover:border-slate-700 transition-all">
                      <input
                        type="file"
                        id="batch-files"
                        multiple={true}
                        onChange={handleBatchFileChange}
                        className="hidden"
                      />
                      
                      <div className="space-y-2.5">
                        <div className="mx-auto p-3 bg-slate-100 dark:bg-slate-950 rounded-full border border-slate-200 dark:border-slate-800 w-fit text-slate-400">
                          <Upload className="w-5 h-5" />
                        </div>
                        <div className="text-xs">
                          <label htmlFor="batch-files" className="font-extrabold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer">
                            Click to upload multiple files
                          </label>
                          <span className="text-slate-500 font-medium"> or drag and drop</span>
                        </div>
                        <p className="text-[10px] text-slate-400">Supports PDF, DOCX, CPP, JAVA, PY, PNG, JPG (Staged limit: 30 files)</p>
                      </div>
                    </div>

                    {/* Staged files counter badge grid */}
                    {batchFiles.length > 0 && (
                      <div className="mt-4 space-y-3">
                        <div className="flex items-center justify-between text-xs font-extrabold text-slate-500">
                          <span>Staged Files ({batchFiles.length} of 30)</span>
                          <button
                            type="button"
                            onClick={() => setBatchFiles([])}
                            className="text-rose-500 hover:underline"
                          >
                            Clear All
                          </button>
                        </div>
                        
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 overflow-y-auto max-h-[150px] pr-1.5">
                          {batchFiles.map((file, i) => (
                            <div key={i} className="flex items-center gap-1.5 p-2 bg-slate-50 dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-850 text-[10px] font-bold text-slate-600 dark:text-slate-350 truncate">
                              <Plus className="w-3.5 h-3.5 text-indigo-500 rotate-45" />
                              <span className="truncate max-w-[120px]">{file.name}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <button
                    type="submit"
                    className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-lg shadow-emerald-600/20 active:scale-98 transition-all cursor-pointer"
                  >
                    Stage Batch & Auto-Extract Names
                  </button>
                </form>
              )}
            </div>
          )}

        </div>
      )}

    </div>
  );
};
