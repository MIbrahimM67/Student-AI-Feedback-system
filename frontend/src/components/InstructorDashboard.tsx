"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api, { API_URL } from "@/lib/api";
import { auth } from "@/lib/firebase";
import { getIdToken } from "firebase/auth";
import { 
  FileSpreadsheet, FileArchive, Upload, Table as TableIcon, 
  CheckCircle2, BadgeCheck, Loader2, Play, Plus, RefreshCw, 
  ClipboardList, HelpCircle, BookOpen, Layers, ArrowLeft,
  FileText, Settings, Terminal
} from "lucide-react";
import { BatchUploadTutorialModal } from "./BatchUploadTutorialModal";

// --- Types ---
interface Subject {
  id: string;
  title: string;
  code: string;
  assignment_count: number;
  reference_count: number;
  kb_status: string;
  expires_at: string;
}

interface Reference {
  id: string;
  title: string;
  type: string;
  index_status: string;
  chunk_count: number;
  created_at: string;
}

interface Assignment {
  id: string;
  title: string;
  prompt: string;
  rubric: string;
}

interface StagedStudent {
  submissionId: string;
  fileName: string;
  extractedName: string;
}

// --- Main Component ---
export const InstructorDashboard: React.FC = () => {
  const { user } = useAuth();
  
  const isVerified = user?.facultyStatus === "approved";
  const isPending = user?.facultyStatus === "pending";

  return (
    <div className="w-full px-5 py-6 space-y-6 animate-fade-in-up">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-[var(--color-rule)]">
        <div>
          <h2 className="text-2xl font-bold text-[var(--color-ink)] flex items-center gap-2">
            <BadgeCheck className="w-6 h-6 text-[var(--color-success)]" />
            Faculty Workbench
          </h2>
          <p className="text-[var(--color-muted)] text-sm mt-1">
            Manage subjects, references, assignments, batch intake, and published reports.
          </p>
        </div>
      </div>

      {!isVerified ? (
        <VerificationForm isPending={isPending} />
      ) : (
        <VerifiedDashboard />
      )}
    </div>
  );
};


// --- VERIFICATION FORM ---
const VerificationForm: React.FC<{ isPending: boolean }> = ({ isPending }) => {
  const [fullName, setFullName] = useState("");
  const [university, setUniversity] = useState("");
  const [department, setDepartment] = useState("");
  const [designation, setDesignation] = useState("");
  const [officialEmail, setOfficialEmail] = useState("");
  const [proofFile, setProofFile] = useState<File | null>(null);
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName || !university || !officialEmail || !proofFile) {
      setError("Please fill out all mandatory fields and upload a faculty proof.");
      return;
    }
    setLoading(true); setError(null);
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
      setSuccess("Verification application submitted successfully.");
    } catch (err: any) {
      setError(err.message || "Failed to submit verification request.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
      <div className="lg:col-span-7 glass-panel p-6 border border-[var(--color-rule)] shadow-[var(--shadow-panel)] space-y-6">
        <div className="space-y-1">
          <h3 className="text-xl font-bold text-[var(--color-ink)]">Faculty Verification Application</h3>
          <p className="text-xs text-[var(--color-muted)]">Provide credentials to unlock subject and batch operations.</p>
        </div>

        {error && <div className="p-4 rounded-xl bg-rose-50 text-rose-600 text-xs font-semibold">{error}</div>}
        {success && <div className="p-4 rounded-xl bg-emerald-50 text-emerald-600 text-xs font-semibold">{success}</div>}

        {isPending || success ? (
          <div className="py-10 text-center space-y-4">
            <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mx-auto" />
            <p className="text-sm font-bold text-slate-700">Application Pending Review</p>
            <p className="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">
              Your verification details have been recorded. System administrators are reviewing your proof sheets.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
             <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase">Full Name</label>
                <input
                  type="text"
                  placeholder="Dr. Sarah Jenkins"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full py-2.5 px-3.5 rounded-xl bg-white border border-slate-200 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase">Official Institution Email</label>
                <input
                  type="email"
                  placeholder="jenkins@qau.edu.pk"
                  value={officialEmail}
                  onChange={(e) => setOfficialEmail(e.target.value)}
                  className="w-full py-2.5 px-3.5 rounded-xl bg-white border border-slate-200 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-1.5 col-span-2">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase">University / Board</label>
                <input
                  type="text"
                  placeholder="Quaid-e-Azam University"
                  value={university}
                  onChange={(e) => setUniversity(e.target.value)}
                  className="w-full py-2.5 px-3.5 rounded-xl bg-white border border-slate-200 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase">Department</label>
                <input
                  type="text"
                  placeholder="Computer Science"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  className="w-full py-2.5 px-3.5 rounded-xl bg-white border border-slate-200 text-xs font-semibold focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-extrabold text-slate-500 uppercase">Faculty Designation</label>
              <input
                type="text"
                placeholder="Assistant Professor / Lecturer"
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
                className="w-full py-2.5 px-3.5 rounded-xl bg-white border border-slate-200 text-xs font-semibold focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-extrabold text-slate-500 uppercase">Employment Proof (PDF / Card)</label>
              <input
                type="file"
                accept="application/pdf,image/*"
                onChange={(e) => setProofFile(e.target.files?.[0] || null)}
                className="w-full py-2 px-3 rounded-xl bg-slate-50 border border-slate-250 text-xs text-slate-500"
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

      <div className="lg:col-span-5 border border-[oklch(96%_0.012_92_/_0.16)] bg-[var(--color-ink)] text-[var(--color-paper)] p-6 shadow-[var(--shadow-panel)] relative overflow-hidden space-y-6">
        <div className="space-y-2">
          <span className="py-1 px-3.5 bg-[oklch(30%_0.045_255)] text-[var(--color-paper)] border border-[var(--color-accent-2)] text-[10px] font-extrabold uppercase tracking-widest">
            Faculty access
          </span>
          <h3 className="text-2xl font-bold tracking-normal text-[var(--color-paper)]">Classroom grading operations</h3>
          <p className="text-xs text-[oklch(82%_0.012_92)] leading-relaxed">
            Verification lets faculty create classrooms, attach reference material, and process student submissions in batches.
          </p>
        </div>
        <div className="border-t border-[oklch(96%_0.012_92_/_0.14)] my-4" />
        <div className="space-y-4">
          <h4 className="text-[10px] font-extrabold text-[oklch(78%_0.014_92)] uppercase tracking-wider">Available after approval</h4>
          <ul className="space-y-3.5 text-xs text-[oklch(86%_0.012_92)]">
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" /> Staged bulk uploads</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" /> Cross-submission plagiarism matching</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" /> Excel summaries export</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[var(--color-success)]" /> Isolated subject classrooms</li>
          </ul>
        </div>
      </div>
    </div>
  );
};


// --- VERIFIED DASHBOARD (Multi-layer View) ---
const VerifiedDashboard: React.FC = () => {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [activeSubject, setActiveSubject] = useState<Subject | null>(null);
  const [activeAssignment, setActiveAssignment] = useState<Assignment | null>(null);
  
  const [loading, setLoading] = useState(true);
  
  // Tutorial State
  const [isTutorialOpen, setIsTutorialOpen] = useState(false);

  useEffect(() => {
    fetchSubjects();
    const hasSeen = localStorage.getItem("hasSeenBatchTutorial");
    if (!hasSeen) setIsTutorialOpen(true);
  }, []);

  const fetchSubjects = async () => {
    setLoading(true);
    try {
      const res = await api.get("/api/instructor/subjects");
      setSubjects(res.data.subjects);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const closeTutorial = () => {
    localStorage.setItem("hasSeenBatchTutorial", "true");
    setIsTutorialOpen(false);
  };

  if (loading && !subjects.length) {
    return <div className="py-20 text-center"><Loader2 className="w-8 h-8 animate-spin mx-auto text-indigo-500" /></div>;
  }

  return (
    <div className="space-y-6">
      
      {/* Navigation Breadcrumbs */}
      <div className="flex items-center gap-2 text-xs font-bold text-[var(--color-muted)] mb-6">
        <button 
          onClick={() => { setActiveSubject(null); setActiveAssignment(null); fetchSubjects(); }} 
          className="hover:text-[var(--color-accent)] transition-colors"
        >
          My Classrooms
        </button>
        {activeSubject && (
          <>
            <span>/</span>
            <button 
              onClick={() => setActiveAssignment(null)} 
              className={`hover:text-[var(--color-accent)] transition-colors ${!activeAssignment ? 'text-[var(--color-accent)]' : ''}`}
            >
              {activeSubject.code}
            </button>
          </>
        )}
        {activeAssignment && (
          <>
            <span>/</span>
            <span className="text-[var(--color-accent)]">{activeAssignment.title}</span>
          </>
        )}
      </div>

      {/* View Routing */}
      {!activeSubject && (
        <SubjectsView subjects={subjects} onSelect={setActiveSubject} onRefresh={fetchSubjects} />
      )}
      
      {activeSubject && !activeAssignment && (
        <SubjectDetailsView subject={activeSubject} onSelectAssignment={setActiveAssignment} />
      )}
      
      {activeSubject && activeAssignment && (
        <AssignmentUploadView subject={activeSubject} assignment={activeAssignment} onTutorial={() => setIsTutorialOpen(true)} />
      )}

      <BatchUploadTutorialModal isOpen={isTutorialOpen} onClose={closeTutorial} />
    </div>
  );
};


// --- LAYER 1: SUBJECTS VIEW ---
const SubjectsView: React.FC<{ subjects: Subject[], onSelect: (s: Subject) => void, onRefresh: () => void }> = ({ subjects, onSelect, onRefresh }) => {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [code, setCode] = useState("");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !code) return;
    try {
      await api.post("/api/instructor/subjects", { title, code });
      setTitle(""); setCode(""); setCreating(false);
      onRefresh();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-[var(--color-ink)]">Your Classrooms</h3>
        <button 
          onClick={() => setCreating(!creating)}
          className="bg-[var(--color-ink)] hover:bg-[var(--color-ink-2)] text-[var(--color-paper)] px-4 py-2 text-xs font-bold inline-flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> New Classroom
        </button>
      </div>

      {creating && (
        <div className="glass-panel p-6 border border-[var(--color-rule)] bg-[var(--color-surface)] shadow-[var(--shadow-panel)] mb-8 relative overflow-hidden">
          <div className="mb-6">
            <h4 className="text-xl font-bold text-[var(--color-ink)]">Create Classroom</h4>
            <p className="text-xs text-[var(--color-muted)] mt-1">Define the subject space where assignments and reference material will live.</p>
          </div>
          <form onSubmit={handleCreate} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
              <div className="space-y-1.5 md:col-span-1">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">Subject Code</label>
                <input 
                  type="text" 
                  placeholder="e.g. CS-101" 
                  value={code} 
                  onChange={e=>setCode(e.target.value)} 
                  className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:font-medium placeholder:text-slate-400" 
                />
              </div>
              <div className="space-y-1.5 md:col-span-3">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">Subject Title</label>
                <input 
                  type="text" 
                  placeholder="e.g. Data Structures and Algorithms" 
                  value={title} 
                  onChange={e=>setTitle(e.target.value)} 
                  className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:font-medium placeholder:text-slate-400" 
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button 
                type="button" 
                onClick={() => setCreating(false)} 
                className="px-5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-500 text-xs font-bold hover:bg-slate-50 transition-all"
              >
                Cancel
              </button>
              <button 
                type="submit" 
                className="px-6 py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 shadow-md shadow-indigo-600/20 active:scale-95 transition-all"
              >
                Create Subject
              </button>
            </div>
          </form>
        </div>
      )}

      {subjects.length === 0 && !creating && (
        <div className="text-center py-20 bg-[var(--color-paper-2)] border border-dashed border-[var(--color-rule-2)]">
          <BookOpen className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <p className="text-sm font-bold text-slate-600">No classrooms created yet.</p>
          <p className="text-xs text-slate-500">Create a subject to begin adding reference materials and grading assignments.</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {subjects.map(sub => {
          const expiresAt = new Date(sub.expires_at);
          const now = new Date();
          const daysLeft = Math.ceil((expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
          const isExpired = daysLeft <= 0;
          const isExpiringSoon = daysLeft <= 14 && daysLeft > 0;
          
          return (
            <div 
              key={sub.id} 
              className={`glass-panel p-5 border transition-all bg-[var(--color-surface)] group flex flex-col ${
                isExpired ? "border-red-200 bg-red-50" : "border-[var(--color-rule)] hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-panel)]"
              }`}
            >
              <div 
                className="flex-1 cursor-pointer"
                onClick={() => !isExpired && onSelect(sub)}
              >
                <div className="flex justify-between items-start mb-4">
                  <span className="bg-slate-100 text-slate-600 text-[10px] font-black px-2.5 py-1 rounded-full uppercase tracking-wider">
                    {sub.code}
                  </span>
                  <Settings className="w-4 h-4 text-slate-300 group-hover:text-indigo-400 transition-colors" />
                </div>
                <h4 className="text-lg font-black text-slate-800 mb-6">{sub.title}</h4>
                <div className="flex gap-4 text-xs font-bold text-slate-500 mb-6">
                  <div className="flex items-center gap-1.5"><Layers className="w-4 h-4 text-indigo-400" /> {sub.assignment_count} Assignments</div>
                  <div className="flex items-center gap-1.5"><BookOpen className="w-4 h-4 text-emerald-400" /> {sub.reference_count} References</div>
                </div>
              </div>
              
              <div className="mt-auto border-t border-slate-100 pt-4 flex items-center justify-between">
                {isExpired ? (
                  <span className="text-[10px] font-bold text-rose-500 uppercase tracking-wider">Archived (Pending Deletion)</span>
                ) : isExpiringSoon ? (
                  <span className="text-[10px] font-bold text-amber-500 uppercase tracking-wider">Expires in {daysLeft} Days</span>
                ) : (
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Active Classroom</span>
                )}
                
                {(isExpired || isExpiringSoon) && (
                  <button 
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        await api.post(`/api/instructor/subjects/${sub.id}/renew`);
                        onRefresh();
                      } catch (err) { console.error(err); }
                    }}
                    className="px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-600 hover:text-white transition-colors text-[10px] font-bold uppercase tracking-wider border border-indigo-200"
                  >
                    Renew
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};


// --- LAYER 2: SUBJECT DETAILS (Assignments & References) ---
const SubjectDetailsView: React.FC<{ subject: Subject, onSelectAssignment: (a: Assignment) => void }> = ({ subject, onSelectAssignment }) => {
  const [tab, setTab] = useState<"assignments"|"references">("assignments");
  
  // Assignment state
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [rubric, setRubric] = useState("");

  // Refs state
  const [refFile, setRefFile] = useState<File|null>(null);
  const [refTitle, setRefTitle] = useState("");
  const [refStatus, setRefStatus] = useState<string|null>(null);
  const [references, setReferences] = useState<Reference[]>([]);
  const [loadingRefs, setLoadingRefs] = useState(false);

  useEffect(() => {
    fetchAssignments();
  }, [subject.id]);

  useEffect(() => {
    if (tab === "references") {
      fetchReferences();
    }
  }, [tab, subject.id]);

  const fetchReferences = async () => {
    setLoadingRefs(true);
    try {
      const res = await api.get(`/api/instructor/subjects/${subject.id}/references`);
      setReferences(res.data.references || []);
    } catch (err) { console.error("Failed to fetch references", err); }
    finally { setLoadingRefs(false); }
  };

  const fetchAssignments = async () => {
    try {
      const res = await api.get(`/api/instructor/subjects/${subject.id}/assignments`);
      setAssignments(res.data.assignments);
    } catch (err) { console.error(err); }
  };

  const handleCreateAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    if(!title) return;
    try {
      await api.post(`/api/instructor/subjects/${subject.id}/assignments`, { title, prompt, rubric });
      setTitle(""); setPrompt(""); setRubric(""); setCreating(false);
      fetchAssignments();
    } catch (err) { console.error(err); }
  };

  const handleUploadRef = async (e: React.FormEvent) => {
    e.preventDefault();
    if(!refTitle || !refFile) return;
    setRefStatus("Uploading and indexing reference material...");
    try {
      const fd = new FormData();
      fd.append("title", refTitle);
      fd.append("file", refFile);
      // Using native fetch instead of Axios to completely bypass any interceptor header mutations
      // that might strip the boundary from the multipart/form-data payload.
      const token = await getIdToken(auth.currentUser!);
      const res = await fetch(`${API_URL}/api/instructor/subjects/${subject.id}/references`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`
        },
        body: fd
      });
      
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText);
      }

      setRefStatus("Success! Knowledge Graph is being updated in the background.");
      setRefTitle(""); setRefFile(null);
    } catch (err: any) { 
      setRefStatus(`Failed: ${err.message || "Could not upload reference."}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 border-b border-slate-200 pb-2">
        <button onClick={()=>setTab("assignments")} className={`pb-2 text-sm font-bold ${tab === "assignments" ? "text-indigo-600 border-b-2 border-indigo-600" : "text-slate-500 hover:text-slate-800"}`}>
          Assignments
        </button>
        <button onClick={()=>setTab("references")} className={`pb-2 text-sm font-bold ${tab === "references" ? "text-indigo-600 border-b-2 border-indigo-600" : "text-slate-500 hover:text-slate-800"}`}>
          Subject Knowledge Base
        </button>
      </div>

      {tab === "assignments" && (
        <div className="space-y-6">
          <div className="flex justify-end">
            <button onClick={()=>setCreating(!creating)} className="bg-[var(--color-ink)] hover:bg-[var(--color-ink-2)] text-[var(--color-paper)] px-4 py-2 text-xs font-bold inline-flex items-center gap-2">
              <Plus className="w-4 h-4"/> Create Assignment
            </button>
          </div>

          {creating && (
            <div className="glass-panel p-6 border border-[var(--color-rule)] bg-[var(--color-surface)] shadow-[var(--shadow-panel)] mb-8 relative overflow-hidden">
              <div className="mb-6">
                <h4 className="text-xl font-bold text-[var(--color-ink)]">Create Assignment</h4>
                <p className="text-xs text-[var(--color-muted)] mt-1">Specify the prompt and rubric criteria for evaluation.</p>
              </div>
              <form onSubmit={handleCreateAssignment} className="space-y-5">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">Assignment Title</label>
                  <input 
                    type="text" 
                    placeholder="e.g. Midterm Examination Part 1" 
                    value={title} 
                    onChange={e=>setTitle(e.target.value)} 
                    className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:font-medium placeholder:text-slate-400" 
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">Assignment Prompt (Question)</label>
                  <textarea 
                    rows={3} 
                    placeholder="e.g. Write a comprehensive essay explaining the effects of..." 
                    value={prompt} 
                    onChange={e=>setPrompt(e.target.value)} 
                    className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:font-medium placeholder:text-slate-400" 
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">Rubric / Grading Criteria</label>
                  <textarea 
                    rows={2} 
                    placeholder="e.g. 50% technical accuracy, 30% clarity, 20% grammar." 
                    value={rubric} 
                    onChange={e=>setRubric(e.target.value)} 
                    className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all placeholder:font-medium placeholder:text-slate-400" 
                  />
                </div>
                <div className="flex justify-end gap-3 pt-2">
                  <button 
                    type="button" 
                    onClick={() => setCreating(false)} 
                    className="px-5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-500 text-xs font-bold hover:bg-slate-50 transition-all"
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit" 
                    className="px-6 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 shadow-md shadow-emerald-600/20 active:scale-95 transition-all"
                  >
                    Save Assignment
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {assignments.map(assn => (
              <div key={assn.id} onClick={() => onSelectAssignment(assn)} className="glass-panel p-5 border border-[var(--color-rule)] hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-panel)] cursor-pointer transition-all bg-[var(--color-surface)]">
                <div className="flex items-center gap-3 mb-3">
                  <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl"><FileText className="w-5 h-5"/></div>
                  <h4 className="text-base font-bold text-[var(--color-ink)]">{assn.title}</h4>
                </div>
                <p className="text-xs text-slate-500 line-clamp-2">{assn.prompt || "No prompt provided."}</p>
              </div>
            ))}
            {assignments.length === 0 && !creating && (
              <div className="col-span-full py-16 text-center text-slate-500 font-medium text-sm">No assignments created yet.</div>
            )}
          </div>
        </div>
      )}

      {tab === "references" && (
        <div className="glass-panel p-6 border border-[var(--color-rule)] bg-[var(--color-surface)] space-y-6">
          <div className="space-y-2">
            <h3 className="text-lg font-black text-slate-800 flex items-center gap-2"><BookOpen className="w-5 h-5 text-emerald-500"/> Subject Knowledge Base</h3>
            <div className="flex items-center gap-3 mt-1">
              <span className={`px-2.5 py-1 text-[10px] font-black uppercase tracking-wider rounded-md border ${
                subject.kb_status === "ready" ? "bg-emerald-50 text-emerald-600 border-emerald-200" :
                subject.kb_status === "indexing" ? "bg-amber-50 text-amber-600 border-amber-200" :
                "bg-slate-100 text-slate-500 border-slate-200"
              }`}>
                {subject.kb_status === "ready" ? "Knowledge Graph: Ready" : subject.kb_status === "indexing" ? "Knowledge Graph: Indexing" : "Knowledge Graph: Empty"}
              </span>
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                {subject.reference_count} References
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed pt-2">
              Upload textbook chapters, marking schemes, or past papers here. The grading pipeline indexes these files for subject-aware evaluation.
            </p>
          </div>
          
          <form onSubmit={handleUploadRef} className="space-y-4 max-w-xl">
             <div className="space-y-1.5">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase">Material Title</label>
                <input type="text" placeholder="Chapter 1: Intro to C++" value={refTitle} onChange={e=>setRefTitle(e.target.value)} className="w-full py-2.5 px-3 rounded-xl bg-white border border-slate-200 text-xs font-semibold focus:outline-none" />
             </div>
             <div className="space-y-1.5">
                <label className="text-[10px] font-extrabold text-slate-500 uppercase">Document (PDF/TXT)</label>
                <input type="file" accept="application/pdf,text/plain" onChange={e=>setRefFile(e.target.files?.[0]||null)} className="w-full py-2 px-3 rounded-xl bg-white border border-slate-200 text-xs text-slate-500" />
             </div>
             <button type="submit" className="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2.5 rounded-xl text-xs font-bold transition-all">Upload & Index</button>
             {refStatus && <div className="text-xs font-bold text-indigo-600 bg-indigo-50 p-3 rounded-xl border border-indigo-100">{refStatus}</div>}
          </form>

          <div className="pt-6 border-t border-slate-200">
            <h4 className="text-sm font-black text-slate-800 mb-4">Indexed Materials</h4>
            {loadingRefs ? (
              <div className="flex items-center justify-center p-8 text-slate-400">
                <Loader2 className="w-6 h-6 animate-spin" />
              </div>
            ) : references.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="py-3 px-4 text-[10px] font-black text-slate-400 uppercase tracking-wider">Material Title</th>
                      <th className="py-3 px-4 text-[10px] font-black text-slate-400 uppercase tracking-wider">Type</th>
                      <th className="py-3 px-4 text-[10px] font-black text-slate-400 uppercase tracking-wider">Status</th>
                      <th className="py-3 px-4 text-[10px] font-black text-slate-400 uppercase tracking-wider text-right">Chunks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {references.map(ref => (
                      <tr key={ref.id} className="border-b border-slate-100 last:border-0 hover:bg-white transition-colors">
                        <td className="py-3 px-4">
                          <div className="text-xs font-bold text-slate-700">{ref.title}</div>
                          <div className="text-[10px] text-slate-400 font-medium">{new Date(ref.created_at).toLocaleString()}</div>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-[10px] font-bold text-slate-500 uppercase">{ref.type.replace('_', ' ')}</span>
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-1 text-[10px] font-bold rounded-md uppercase tracking-wider ${
                            ref.index_status === 'embedded' ? 'bg-emerald-50 text-emerald-600' :
                            ref.index_status === 'failed' ? 'bg-rose-50 text-rose-600' :
                            'bg-amber-50 text-amber-600'
                          }`}>
                            {ref.index_status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right text-xs font-bold text-slate-500">
                          {ref.chunk_count > 0 ? ref.chunk_count : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-xs font-medium text-slate-500 bg-white rounded-2xl border border-dashed border-slate-200">
                No reference materials added yet.
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
};


// --- LAYER 3: ASSIGNMENT UPLOAD ZONE ---
const AssignmentUploadView: React.FC<{ subject: Subject, assignment: Assignment, onTutorial: () => void }> = ({ subject, assignment, onTutorial }) => {
  const [uploadMode, setUploadMode] = useState<"single" | "batch" | "history">("single");

  // Shared state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [successMsg, setSuccessMsg] = useState<string|null>(null);
  const [fileType, setFileType] = useState("text");

  // Single Upload State
  const [studentName, setStudentName] = useState("");
  const [singleFile, setSingleFile] = useState<File|null>(null);

  // Batch Upload State
  const [batchFile, setBatchFile] = useState<File|null>(null);
  const [batchId, setBatchId] = useState<string|null>(null);
  const [stagedStudents, setStagedStudents] = useState<any[]>([]);
  
  // Polling State
  const [gradingProgress, setGradingProgress] = useState<any>(null);
  const [pollIntervalId, setPollIntervalId] = useState<NodeJS.Timeout|null>(null);

  // Batch Review State
  const [batchReports, setBatchReports] = useState<any[]>([]);
  const [reviewingReports, setReviewingReports] = useState(false);

  // History State
  const [historyBatches, setHistoryBatches] = useState<any[]>([]);
  const [batchName, setBatchName] = useState("");
  const [renamingBatchId, setRenamingBatchId] = useState<string|null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [expandedReportId, setExpandedReportId] = useState<string|null>(null);
  const [reportDetails, setReportDetails] = useState<Record<string, any>>({});

  const handleSingleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if(!studentName || !singleFile) return setError("Name and file required.");
    setLoading(true); setError(null); setSuccessMsg(null);
    try {
      const fd = new FormData();
      fd.append("assignment_id", assignment.id);
      fd.append("subject_id", subject.id);
      fd.append("student_name", studentName);
      fd.append("type", fileType);
      fd.append("file", singleFile);

      const token = await auth.currentUser?.getIdToken();
      if (!token) throw new Error("Authentication failed");

      const res = await fetch(`${API_URL}/api/instructor/single-upload`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`
        },
        body: fd
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to upload.");
      }

      const resData = await res.json();
      setSuccessMsg(`Submission for ${studentName} queued for grading!`);
      if (resData.batch_id) {
        setBatchId(resData.batch_id);
        startPollingProgress(resData.batch_id);
      }
      setStudentName(""); setSingleFile(null);
    } catch(err: any) {
      setError(err.message || "Failed to upload.");
    } finally {
      setLoading(false);
    }
  };

  const handleStageBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if(!batchFile) return setError("ZIP file required.");
    setLoading(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("assignment_id", assignment.id);
      fd.append("subject_id", subject.id);
      fd.append("type", fileType);
      fd.append("file", batchFile);
      if (batchName.trim()) fd.append("batch_name", batchName.trim());

      const token = await auth.currentUser?.getIdToken();
      if (!token) throw new Error("Authentication failed");

      const res = await fetch(`${API_URL}/api/instructor/batch`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: fd
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Batch staging failed.");
      }

      const resData = await res.json();
      setBatchId(resData.batch_id);
      setSuccessMsg(resData.message);
      setBatchFile(null); setBatchName("");
      setStagedStudents([]);
      startPollingProgress(resData.batch_id);
    } catch(err:any) {
      setError(err.message || "Batch staging failed.");
    } finally { setLoading(false); }
  };

  const handleConfirmBatch = async () => {
    if(!batchId) return;
    setLoading(true); setError(null);
    try {
      const namesMapping = stagedStudents.map(s => ({ submissionId: s.submissionId, studentName: s.extractedName }));
      await api.post(`/api/instructor/batch/${batchId}/confirm-names`, { names: namesMapping });
      await api.post(`/api/instructor/batch/${batchId}/process`);
      
      setSuccessMsg("Bulk grading started!");
      setStagedStudents([]); setBatchFile(null);
      startPollingProgress(batchId);
    } catch(err:any) { setError(err.message); }
    finally { setLoading(false); }
  };

  const startPollingProgress = (id: string) => {
    if (pollIntervalId) clearInterval(pollIntervalId);
    const poll = async () => {
      try {
        const res = await api.get(`/api/instructor/batch/${id}`);
        setGradingProgress(res.data);
        const processed = (res.data.processed_files || 0) + (res.data.needs_review_count || 0);
        if (processed >= (res.data.total_files || 0) && res.data.total_files > 0) {
          if (pollIntervalId) clearInterval(pollIntervalId);
          setPollIntervalId(null);
          return true;
        }
      } catch (err) {}
      return false;
    };
    poll();
    const interval = setInterval(async () => {
      const done = await poll();
      if (done) clearInterval(interval);
    }, 3000);
    setPollIntervalId(interval);
  };

  const fetchBatchReports = async (id: string) => {
    try {
      setReviewingReports(true);
      setBatchId(id);
      const res = await api.get(`/api/instructor/batch/${id}/reports`);
      setBatchReports(res.data.reports || []);
    } catch (err: any) {
      setError(err.message || "Failed to fetch reports.");
    }
  };

  const fetchAssignmentHistory = async () => {
    try {
      const res = await api.get(`/api/instructor/assignments/${assignment.id}/batches`);
      setHistoryBatches(res.data.batches || []);
    } catch (err: any) {
      console.error(err);
    }
  };

  const handleRenameBatch = async (batchId: string) => {
    if (!renameValue.trim()) return;
    try {
      await api.patch(`/api/instructor/batch/${batchId}/name`, { batch_name: renameValue.trim() });
      setHistoryBatches(prev => prev.map(b => b.id === batchId ? { ...b, batch_name: renameValue.trim() } : b));
      setRenamingBatchId(null); setRenameValue("");
    } catch (err: any) { setError(err.message || "Rename failed."); }
  };

  const handleDeleteBatch = async (batchId: string, batchName: string) => {
    if (!confirm(`Delete batch "${batchName}"? This will permanently remove all grading data.`)) return;
    try {
      await api.delete(`/api/instructor/batch/${batchId}`);
      setHistoryBatches(prev => prev.filter(b => b.id !== batchId));
    } catch (err: any) { setError(err.message || "Delete failed."); }
  };

  const handleApproveReport = async (reportId: string, finalScore: number) => {
    try {
      await api.post(`/api/instructor/batch/${batchId}/reports/${reportId}/approve`, {
         final_payload: null 
      });
      fetchBatchReports(batchId!);
    } catch (err: any) {
      setError(err.message || "Approval failed.");
    }
  };

  const fetchReportDetail = async (reportId: string) => {
    if (reportDetails[reportId]) return; // already loaded
    try {
      const res = await api.get(`/api/instructor/reports/${reportId}`);
      setReportDetails(prev => ({ ...prev, [reportId]: res.data }));
    } catch (err: any) {
      console.error("Failed to load report detail", err);
    }
  };

  useEffect(() => {
    return () => { if(pollIntervalId) clearInterval(pollIntervalId); };
  }, [pollIntervalId]);

  useEffect(() => {
    if (uploadMode === 'history') {
      fetchAssignmentHistory();
    }
  }, [uploadMode]);

  const progressPercent = Math.max(0, Math.min(100, Math.round(
    gradingProgress?.progress_percent ??
    (((gradingProgress?.processed_files || 0) + (gradingProgress?.needs_review_count || 0)) / Math.max(1, gradingProgress?.total_files || 1)) * 100
  )));
  const activeStage = gradingProgress?.active_stage || "queued";
  const progressStages = [
    { label: "Evidence", aliases: ["queued", "extracting", "evidence_ready", "reference_extracting"] },
    { label: "Checks", aliases: ["policy_scan", "code_checks", "context_building"] },
    { label: "Routing", aliases: ["ingesting_submission", "ingesting_reference", "decomposing_rubric", "routing"] },
    { label: "Review", aliases: ["chunk_review", "retrieving_reference", "specialist"] },
    { label: "Audit", aliases: ["judge"] },
    { label: "Report", aliases: ["senior", "finalizing", "completed"] },
  ];
  const activeStageIndex = Math.max(0, progressStages.findIndex(stage => stage.aliases.includes(activeStage)));

  return (
    <div className="space-y-6">
      
      {/* Current Assignment Context */}
      <div className="glass-panel p-5 border border-[var(--color-rule)] bg-[var(--color-surface)] flex flex-col gap-4 sm:flex-row sm:justify-between sm:items-center">
        <div>
           <h3 className="text-xl font-black text-slate-800">{assignment.title}</h3>
           <p className="text-xs text-slate-500 line-clamp-1 max-w-2xl mt-1"><span className="font-bold">Prompt:</span> {assignment.prompt}</p>
        </div>
        <button onClick={onTutorial} className="text-xs font-bold text-[var(--color-muted)] hover:text-[var(--color-accent)] bg-[var(--color-surface)] border border-[var(--color-rule)] px-3 py-1.5 flex items-center gap-1.5">
          <HelpCircle className="w-3.5 h-3.5"/> Batch Tutorial
        </button>
      </div>

      <div className="flex gap-4">
         <button onClick={()=>setUploadMode("single")} className={`flex-1 py-4 border font-bold text-sm transition-all ${uploadMode === "single" ? "border-[var(--color-accent)] bg-blue-50 text-[var(--color-accent)]" : "border-[var(--color-rule)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:border-[var(--color-rule-2)]"}`}>
            Single Submission Upload
         </button>
         <button onClick={()=>setUploadMode("batch")} className={`flex-1 py-4 border font-bold text-sm transition-all ${uploadMode === "batch" ? "border-[var(--color-success)] bg-green-50 text-[var(--color-success)]" : "border-[var(--color-rule)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:border-[var(--color-rule-2)]"}`}>
            Classroom Batch (Master ZIP)
         </button>
         <button onClick={()=>setUploadMode("history")} className={`flex-1 py-4 border font-bold text-sm transition-all ${uploadMode === "history" ? "border-[var(--color-warning)] bg-amber-50 text-[var(--color-warning)]" : "border-[var(--color-rule)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:border-[var(--color-rule-2)]"}`}>
            Grading History
         </button>
      </div>

      {error && <div className="p-4 rounded-xl bg-rose-50 text-rose-600 text-xs font-semibold">{error}</div>}
      {successMsg && <div className="p-4 rounded-xl bg-emerald-50 text-emerald-600 text-xs font-semibold">{successMsg}</div>}

      {gradingProgress && !reviewingReports && (
         <div className="glass-panel p-6 border border-[var(--color-rule)] shadow-[var(--shadow-panel)] space-y-6 bg-[var(--color-surface)]">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[var(--color-muted)]">Live AI Pipeline</p>
                <h3 className="mt-1 text-lg font-black text-slate-800">
                  {((gradingProgress.processed_files + gradingProgress.needs_review_count) >= gradingProgress.total_files) ? "Grading complete" : "Grading in progress"}
                </h3>
                <p className="mt-2 max-w-2xl text-xs font-semibold leading-relaxed text-slate-500">
                  {gradingProgress.progress_message || "Preparing the grading worker."}
                </p>
              </div>
              <div className="min-w-[140px] text-left lg:text-right">
                <div className="text-3xl font-black text-slate-900">{progressPercent}%</div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {(gradingProgress.processed_files || 0) + (gradingProgress.needs_review_count || 0)} of {gradingProgress.total_files || 0} ready
                </div>
              </div>
            </div>

            <div className="w-full bg-slate-100 h-3.5 rounded-full overflow-hidden border border-slate-200">
               <div className="bg-[var(--color-accent)] h-full transition-all duration-700" style={{width: `${progressPercent}%`}} />
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {progressStages.map((stage, index) => {
                const isDone = progressPercent >= 100 || index < activeStageIndex;
                const isActive = index === activeStageIndex && progressPercent < 100;
                return (
                  <div key={stage.label} className={`border px-3 py-3 ${isActive ? "border-[var(--color-accent)] bg-blue-50" : isDone ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}>
                    <div className="flex items-center gap-2">
                      {isDone ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      ) : isActive ? (
                        <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
                      ) : (
                        <span className="h-4 w-4 rounded-full border border-slate-300" />
                      )}
                      <span className={`text-[11px] font-black ${isActive ? "text-[var(--color-accent)]" : isDone ? "text-emerald-700" : "text-slate-400"}`}>{stage.label}</span>
                    </div>
                  </div>
                );
              })}
            </div>
            
            {((gradingProgress.processed_files + gradingProgress.needs_review_count) >= gradingProgress.total_files) && (
              <div className="flex gap-4 pt-4 border-t border-slate-100">
                <button onClick={() => fetchBatchReports(gradingProgress.id)} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 transition-colors text-white px-5 py-2.5 rounded-xl text-xs font-bold shadow-md">
                   <ClipboardList className="w-4 h-4"/> Review {gradingProgress.total_files} Graded Submissions
                </button>
                <button onClick={()=>setGradingProgress(null)} className="ml-auto text-xs font-bold text-slate-400">Clear</button>
              </div>
            )}
         </div>
      )}

      {reviewingReports && (
         <div className="glass-panel p-6 border border-[var(--color-rule)] shadow-[var(--shadow-panel)] space-y-6 bg-[var(--color-surface)]">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-black text-slate-800 flex items-center gap-2"><ClipboardList className="w-5 h-5 text-indigo-500"/> Batch Reports Review</h3>
              <div className="flex items-center gap-3">
                 <button onClick={() => {
                   auth.currentUser?.getIdToken().then((token: string) => {
                     fetch(`${API_URL}/api/instructor/batch/${batchId}/export/excel`, { headers: { Authorization: `Bearer ${token}` } })
                       .then(res => res.blob()).then(blob => {
                         const url = window.URL.createObjectURL(blob);
                         const a = document.createElement('a'); a.href = url; a.download = `Batch_Grades_${batchId}.xlsx`; a.click();
                       });
                   });
                 }} className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 bg-emerald-50 hover:bg-emerald-100 px-3 py-1.5 rounded-lg transition-colors">
                   <FileSpreadsheet className="w-4 h-4"/> Export Excel
                 </button>
                 <button onClick={() => {
                   auth.currentUser?.getIdToken().then((token: string) => {
                     fetch(`${API_URL}/api/instructor/batch/${batchId}/export/zip`, { headers: { Authorization: `Bearer ${token}` } })
                       .then(res => res.blob()).then(blob => {
                         const url = window.URL.createObjectURL(blob);
                         const a = document.createElement('a'); a.href = url; a.download = `Batch_Reports_${batchId}.zip`; a.click();
                       });
                   });
                 }} className="flex items-center gap-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors">
                   <FileArchive className="w-4 h-4"/> Export Summaries
                 </button>
                 <div className="w-px h-5 bg-slate-200 mx-1"></div>
                 <button onClick={() => setReviewingReports(false)} className="text-xs font-bold text-slate-400 hover:text-slate-600">Close Review</button>
              </div>
            </div>
            <div className="overflow-x-auto border border-slate-200 rounded-2xl">
               <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-extrabold sticky top-0">
                     <tr>
                        <th className="p-4 uppercase tracking-wider">Student</th>
                        <th className="p-4 uppercase tracking-wider">AI Score</th>
                        <th className="p-4 uppercase tracking-wider">Confidence</th>
                        <th className="p-4 uppercase tracking-wider">Status</th>
                        <th className="p-4 uppercase tracking-wider text-right">Action</th>
                     </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                      {batchReports.map((report) => {
                        const isExpanded = expandedReportId === report.report_id;
                        const detail = reportDetails[report.report_id];
                        return (
                          <React.Fragment key={report.submission_id}>
                            <tr
                              className="hover:bg-slate-50 transition-colors cursor-pointer"
                              onClick={() => {
                                if (isExpanded) { setExpandedReportId(null); }
                                else { setExpandedReportId(report.report_id); if (report.report_id) fetchReportDetail(report.report_id); }
                              }}
                            >
                              <td className="p-4">
                                <div className="flex items-center gap-2">
                                  <span className={`text-slate-400 transition-transform text-xs ${isExpanded ? 'rotate-90' : ''}`}>▶</span>
                                  <div>
                                    <div className="font-bold text-slate-700 text-sm">{report.student_name}</div>
                                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">{report.file_name}</div>
                                  </div>
                                </div>
                              </td>
                              <td className="p-4">
                                 {report.submission_status === 'failed' ? (
                                   <div className="text-xs font-bold text-rose-500">Processing Failed</div>
                                 ) : !report.report_id ? (
                                   <div>
                                     <div className="text-xs font-black text-slate-700">{report.progress_percent || 0}%</div>
                                     <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-slate-200">
                                       <div className="h-full bg-[var(--color-accent)]" style={{ width: `${report.progress_percent || 0}%` }} />
                                     </div>
                                   </div>
                                 ) : (
                                   <div className="text-xl font-black text-slate-800">{report.final_status ? report.final_status === 'pass' ? report.final_overall_score || report.ai_overall_score : report.ai_overall_score : report.ai_overall_score}<span className="text-xs text-slate-400 font-medium">/{report.ai_max_score}</span></div>
                                 )}
                              </td>
                              <td className="p-4">
                                 {report.submission_status === 'failed' ? (
                                   <span className="text-xs text-slate-400">—</span>
                                 ) : (
                                   <div className="flex items-center gap-1.5">
                                     <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                       <div className={`h-full ${report.ai_overall_confidence > 0.8 ? 'bg-emerald-500' : report.ai_overall_confidence > 0.6 ? 'bg-amber-500' : 'bg-rose-500'}`} style={{width: `${(report.ai_overall_confidence || 0) * 100}%`}}/>
                                     </div>
                                     <span className="text-[10px] font-bold text-slate-500">{Math.round((report.ai_overall_confidence || 0) * 100)}%</span>
                                   </div>
                                 )}
                              </td>
                              <td className="p-4">
                                 <span className={`px-2.5 py-1 text-[10px] font-black uppercase tracking-wider rounded-md border ${
                                   report.submission_status === 'failed' ? "bg-rose-50 text-rose-600 border-rose-200" :
                                   report.published_at ? "bg-emerald-50 text-emerald-600 border-emerald-200" :
                                   "bg-amber-50 text-amber-600 border-amber-200"
                                 }`}>
                                   {report.submission_status === 'failed' ? "Failed" : report.published_at ? "Approved" : "Needs Review"}
                                 </span>
                              </td>
                              <td className="p-4 text-right" onClick={e => e.stopPropagation()}>
                                 {report.submission_status === 'failed' ? (
                                   <span className="text-xs font-bold text-rose-400">Error</span>
                                 ) : !report.report_id ? (
                                   <span className="text-xs font-bold text-slate-400">Working</span>
                                 ) : !report.published_at ? (
                                   <button onClick={() => handleApproveReport(report.report_id, report.ai_overall_score)} className="bg-white border border-indigo-200 text-indigo-600 hover:bg-indigo-50 px-4 py-1.5 rounded-lg text-xs font-bold transition-colors">
                                     Approve
                                   </button>
                                 ) : (
                                   <span className="text-xs font-bold text-slate-400">Published</span>
                                 )}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr key={`${report.submission_id}-detail`} className="bg-indigo-50/50 border-b border-indigo-100">
                                <td colSpan={5} className="px-6 py-5">
                                  {!detail ? (
                                    <div className="text-xs text-slate-400 animate-pulse">Loading feedback...</div>
                                  ) : (
                                    <div className="space-y-4">
                                      {/* AI Feedback */}
                                      <div className="bg-white rounded-xl border border-slate-200 p-4">
                                        <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider mb-2">AI Feedback</div>
                                        <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">{detail.ai_payload?.feedback || 'No feedback available.'}</p>
                                      </div>
                                      {/* Per-Criterion Breakdown */}
                                      {detail.ai_payload?.per_criterion && Object.keys(detail.ai_payload.per_criterion).length > 0 && (
                                        <div className="bg-white rounded-xl border border-slate-200 p-4">
                                          <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider mb-3">Criteria Breakdown</div>
                                          <div className="space-y-2">
                                            {Object.entries(detail.ai_payload.per_criterion).map(([criterionId, score]: [string, any]) => (
                                              <div key={criterionId} className="flex items-center justify-between text-xs">
                                                <span className="font-medium text-slate-600 capitalize">{criterionId.replace(/_/g, ' ')}</span>
                                                <span className={`font-bold px-2 py-0.5 rounded-md ${
                                                  Number(score) === 0 ? 'bg-rose-50 text-rose-600' :
                                                  Number(score) >= 4 ? 'bg-emerald-50 text-emerald-600' :
                                                  'bg-amber-50 text-amber-600'
                                                }`}>{score} pts</span>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                      {/* Sandbox Logs */}
                                      {detail.ai_payload?.sandbox_logs && detail.ai_payload.sandbox_logs.length > 0 && (
                                        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 font-mono">
                                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                            <Terminal className="w-3 h-3" /> Sandbox Execution Logs
                                          </div>
                                          <div className="space-y-3">
                                            {detail.ai_payload.sandbox_logs.map((log: any, i: number) => (
                                              <div key={i} className="text-[10px] space-y-1">
                                                <div className="flex items-center gap-2 text-indigo-400">
                                                  <span className="font-bold">Test Case {i+1}</span>
                                                  {log.passed ? (
                                                    <span className="text-emerald-400">✓ Passed</span>
                                                  ) : (
                                                    <span className="text-rose-400">✗ Failed</span>
                                                  )}
                                                </div>
                                                <div className="text-slate-300">
                                                  <span className="text-slate-500">Input:</span> {log.input}
                                                </div>
                                                <div className="text-slate-300">
                                                  <span className="text-slate-500">Expected:</span> {log.expected_output}
                                                </div>
                                                <div className="text-slate-300">
                                                  <span className="text-slate-500">Actual:</span> {log.actual_output}
                                                </div>
                                                {log.error && (
                                                  <div className="text-rose-400 break-words mt-1 bg-rose-500/10 p-2 rounded">
                                                    {log.error}
                                                  </div>
                                                )}
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                     })}
                  </tbody>
               </table>
            </div>
         </div>
      )}

      {/* SINGLE UPLOAD FORM */}
      {uploadMode === "single" && !gradingProgress && (
        <form onSubmit={handleSingleUpload} className="glass-panel p-6 border border-[var(--color-rule)] shadow-[var(--shadow-panel)] bg-[var(--color-surface)] space-y-6">
           <h3 className="text-lg font-black text-slate-800 flex items-center gap-2"><Upload className="w-5 h-5 text-indigo-500"/> Single Student Grading</h3>
           <div className="grid grid-cols-2 gap-6">
              <div className="space-y-1.5">
                 <label className="text-[10px] font-extrabold text-slate-500 uppercase">Student Name / ID</label>
                 <input type="text" value={studentName} onChange={e=>setStudentName(e.target.value)} className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:border-indigo-500" placeholder="e.g. John Doe - CS101"/>
              </div>
              <div className="space-y-1.5">
                 <label className="text-[10px] font-extrabold text-slate-500 uppercase">Submission Format</label>
                 <select value={fileType} onChange={e=>setFileType(e.target.value)} className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none">
                    <option value="text">Digital Document (PDF/TXT/DOCX)</option>
                    <option value="handwritten">Handwritten Scan (OCR)</option>
                    <option value="coding">Programming Code</option>
                 </select>
              </div>
           </div>
           <div className="space-y-1.5">
              <label className="text-[10px] font-extrabold text-slate-500 uppercase">Submission File</label>
              <input type="file" onChange={e=>setSingleFile(e.target.files?.[0]||null)} className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-500" />
           </div>
           <button type="submit" disabled={loading} className="w-full py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-lg active:scale-98 transition-all disabled:opacity-50">
             {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto"/> : "Submit for Evaluation"}
           </button>
        </form>
      )}

      {/* BATCH UPLOAD FORM */}
      {uploadMode === "batch" && !gradingProgress && (
        <div className="glass-panel p-6 border border-[var(--color-rule)] shadow-[var(--shadow-panel)] bg-[var(--color-surface)] space-y-6">
          
          {stagedStudents.length > 0 ? (
            <div className="space-y-4">
              <h3 className="text-lg font-black text-slate-800">Confirm Student Names</h3>
              <div className="max-h-96 overflow-y-auto border border-slate-200 rounded-2xl">
                 <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-extrabold sticky top-0">
                       <tr><th className="p-4">Filename</th><th className="p-4">Student Name (Edit)</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                       {stagedStudents.map((s, i) => (
                         <tr key={i} className="hover:bg-slate-50">
                            <td className="p-4 font-mono font-bold text-slate-600">{s.fileName}</td>
                            <td className="p-3">
                               <input type="text" value={s.extractedName} onChange={(e) => {
                                 const copy = [...stagedStudents];
                                 copy[i].extractedName = e.target.value;
                                 setStagedStudents(copy);
                               }} className="w-full p-2 border border-slate-200 rounded-lg bg-white" />
                            </td>
                         </tr>
                       ))}
                    </tbody>
                 </table>
              </div>
              <div className="flex gap-4 justify-end pt-4">
                 <button onClick={()=>setStagedStudents([])} className="px-5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-500 font-bold text-xs hover:bg-slate-50">Cancel</button>
                 <button onClick={handleConfirmBatch} className="px-5 py-2.5 rounded-xl bg-indigo-600 text-white font-bold text-xs hover:bg-indigo-700 flex items-center gap-2 shadow-md"><Play className="w-4 h-4"/> Confirm & Grade All</button>
              </div>
            </div>
          ) : (
                  <form onSubmit={handleStageBatch} className="space-y-6">
              <h3 className="text-lg font-black text-slate-800 flex items-center gap-2"><ClipboardList className="w-5 h-5 text-emerald-500"/> Batch ZIP Upload</h3>
              <div className="space-y-1.5">
                 <label className="text-[10px] font-extrabold text-slate-500 uppercase">Batch Name <span className="text-slate-400 font-normal normal-case">(optional)</span></label>
                 <input type="text" value={batchName} onChange={e=>setBatchName(e.target.value)} className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none focus:border-emerald-500" placeholder='e.g. "Midterm Exam — Batch A"' />
              </div>
              <div className="space-y-1.5">
                 <label className="text-[10px] font-extrabold text-slate-500 uppercase">Submissions Format</label>
                 <select value={fileType} onChange={e=>setFileType(e.target.value)} className="w-full py-3 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-bold focus:outline-none">
                    <option value="text">Digital Documents (PDF/TXT/DOCX folders)</option>
                    <option value="handwritten">Handwritten Scans (OCR)</option>
                    <option value="coding">Programming Code Projects</option>
                 </select>
              </div>
              <div className="space-y-1.5">
                 <label className="text-[10px] font-extrabold text-slate-500 uppercase">Master ZIP File</label>
                 <input type="file" accept=".zip" onChange={e=>setBatchFile(e.target.files?.[0]||null)} className="w-full py-8 px-4 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 text-slate-500 text-sm font-bold text-center file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100" />
                 <p className="text-[10px] text-slate-400 mt-2">Upload a single .zip file containing folders for each student. Max 30 folders / 100MB.</p>
              </div>
              <button type="submit" disabled={loading} className="w-full py-3.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-lg active:scale-98 transition-all disabled:opacity-50">
                 {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto"/> : "Stage Batch & Extract Names"}
              </button>
            </form>
          )}
        </div>
      )}

      {uploadMode === "history" && !reviewingReports && (
        <div className="glass-panel p-6 border border-[var(--color-rule)] shadow-[var(--shadow-panel)] bg-[var(--color-surface)] space-y-6">
          <h3 className="text-lg font-black text-slate-800 flex items-center gap-2"><ClipboardList className="w-5 h-5 text-amber-500"/> Past Grading Batches</h3>
          
          {historyBatches.length > 0 ? (
            <div className="overflow-x-auto border border-slate-200 rounded-2xl">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-extrabold sticky top-0">
                  <tr>
                    <th className="p-4 uppercase tracking-wider">Batch Name</th>
                    <th className="p-4 uppercase tracking-wider">Date</th>
                    <th className="p-4 uppercase tracking-wider">Progress</th>
                    <th className="p-4 uppercase tracking-wider">Status</th>
                    <th className="p-4 uppercase tracking-wider text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {historyBatches.map(hb => {
                    const processed = (hb.processed_files || 0) + (hb.needs_review_count || 0);
                    const isDone = processed >= hb.total_files && hb.total_files > 0;
                    const displayName = hb.batch_name || `Batch ${hb.id.split("-")[0]}`;
                    
                    return (
                      <tr key={hb.id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-4">
                          {renamingBatchId === hb.id ? (
                            <div className="flex items-center gap-2">
                              <input
                                type="text"
                                value={renameValue}
                                onChange={e => setRenameValue(e.target.value)}
                                onKeyDown={e => { if(e.key === 'Enter') handleRenameBatch(hb.id); if(e.key === 'Escape') { setRenamingBatchId(null); setRenameValue(""); } }}
                                autoFocus
                                className="flex-1 py-1.5 px-2 border border-emerald-300 rounded-lg text-xs font-bold focus:outline-none focus:border-emerald-500 bg-white"
                              />
                              <button onClick={() => handleRenameBatch(hb.id)} className="text-emerald-600 font-bold text-xs hover:text-emerald-700">Save</button>
                              <button onClick={() => { setRenamingBatchId(null); setRenameValue(""); }} className="text-slate-400 font-bold text-xs hover:text-slate-600">✕</button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 group">
                              <span className="font-bold text-slate-700">{displayName}</span>
                              <button
                                onClick={() => { setRenamingBatchId(hb.id); setRenameValue(displayName); }}
                                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-indigo-500 transition-all text-[10px] font-bold"
                                title="Rename"
                              >✎</button>
                            </div>
                          )}
                        </td>
                        <td className="p-4 text-slate-500">{new Date(hb.created_at).toLocaleDateString()}</td>
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                             <div className="w-24 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                               <div className="bg-amber-500 h-full" style={{width: `${(processed / Math.max(1, hb.total_files)) * 100}%`}}/>
                             </div>
                             <span className="text-[10px] font-bold text-slate-500">{processed}/{hb.total_files}</span>
                          </div>
                        </td>
                        <td className="p-4">
                           <span className={`px-2.5 py-1 text-[10px] font-black uppercase tracking-wider rounded-md border ${
                             isDone ? "bg-emerald-50 text-emerald-600 border-emerald-200" :
                             "bg-amber-50 text-amber-600 border-amber-200"
                           }`}>
                             {isDone ? "Completed" : "Processing"}
                           </span>
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button 
                              onClick={() => { setBatchId(hb.id); fetchBatchReports(hb.id); }} 
                              disabled={!isDone}
                              className="bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
                            >
                              View Reports
                            </button>
                            <button
                              onClick={() => handleDeleteBatch(hb.id, displayName)}
                              className="bg-white border border-rose-200 text-rose-500 hover:bg-rose-50 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors"
                              title="Delete batch"
                            >
                              🗑
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-xs font-medium text-slate-500 border border-dashed border-slate-200 rounded-2xl">
               No past batches found for this assignment.
            </div>
          )}
        </div>
      )}
    </div>
  );
};
