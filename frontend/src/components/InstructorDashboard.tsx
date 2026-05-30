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
  FileText, Settings
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
    <div className="max-w-6xl w-full mx-auto px-4 py-8 space-y-10 animate-fade-in-up">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <h2 className="text-3xl font-black text-slate-800 flex items-center gap-2">
            <BadgeCheck className="w-7 h-7 text-emerald-500 animate-float" />
            Instructor Dashboard
          </h2>
          <p className="text-slate-500 text-sm mt-1">
            Manage subjects, assignments, references, and AI evaluations.
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
      <div className="lg:col-span-7 glass-panel p-8 rounded-3xl border border-slate-200 shadow-xl space-y-6">
        <div className="space-y-1">
          <h3 className="text-xl font-black text-slate-800">Faculty Verification Application</h3>
          <p className="text-xs text-slate-500">Provide credentials to unlock batch operations and pro features.</p>
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
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Staged Bulk Uploads (up to 30 files / 100MB)</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Cross-submission Plagiarism matching</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Excel summaries export</li>
            <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Create isolated subject classrooms</li>
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
      <div className="flex items-center gap-2 text-xs font-bold text-slate-500 mb-6">
        <button 
          onClick={() => { setActiveSubject(null); setActiveAssignment(null); fetchSubjects(); }} 
          className="hover:text-indigo-600 transition-colors"
        >
          My Classrooms
        </button>
        {activeSubject && (
          <>
            <span>/</span>
            <button 
              onClick={() => setActiveAssignment(null)} 
              className={`hover:text-indigo-600 transition-colors ${!activeAssignment ? 'text-indigo-600' : ''}`}
            >
              {activeSubject.code}
            </button>
          </>
        )}
        {activeAssignment && (
          <>
            <span>/</span>
            <span className="text-indigo-600">{activeAssignment.title}</span>
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
        <h3 className="text-lg font-black text-slate-800">Your Classrooms</h3>
        <button 
          onClick={() => setCreating(!creating)}
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-xs font-bold inline-flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> New Classroom
        </button>
      </div>

      {creating && (
        <div className="glass-panel p-8 rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-200/50 mb-8 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full blur-2xl -z-10" />
          <div className="mb-6">
            <h4 className="text-xl font-black text-slate-800">Launch a New Classroom</h4>
            <p className="text-xs text-slate-500 mt-1">Define the subject space where assignments and knowledge bases will live.</p>
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
        <div className="text-center py-20 bg-slate-50 rounded-3xl border border-dashed border-slate-300">
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
              className={`glass-panel p-6 rounded-3xl border transition-all bg-white group flex flex-col ${
                isExpired ? "border-rose-300 bg-rose-50/30" : "border-slate-200 hover:border-indigo-300 hover:shadow-lg"
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

  // Refs state (stubbed for UI, handles API separately)
  const [refFile, setRefFile] = useState<File|null>(null);
  const [refTitle, setRefTitle] = useState("");
  const [refStatus, setRefStatus] = useState<string|null>(null);

  useEffect(() => {
    fetchAssignments();
  }, [subject.id]);

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
            <button onClick={()=>setCreating(!creating)} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-xs font-bold inline-flex items-center gap-2">
              <Plus className="w-4 h-4"/> Create Assignment
            </button>
          </div>

          {creating && (
            <div className="glass-panel p-8 rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-200/50 mb-8 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl -z-10" />
              <div className="mb-6">
                <h4 className="text-xl font-black text-slate-800">Draft New Assignment</h4>
                <p className="text-xs text-slate-500 mt-1">Specify the prompt and rubric criteria for AI evaluation.</p>
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
              <div key={assn.id} onClick={() => onSelectAssignment(assn)} className="glass-panel p-6 rounded-3xl border border-slate-200 hover:border-indigo-300 hover:shadow-lg cursor-pointer transition-all bg-white">
                <div className="flex items-center gap-3 mb-3">
                  <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl"><FileText className="w-5 h-5"/></div>
                  <h4 className="text-base font-black text-slate-800">{assn.title}</h4>
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
        <div className="glass-panel p-8 rounded-3xl border border-slate-200 bg-slate-50 space-y-6">
          <div className="space-y-2">
            <h3 className="text-lg font-black text-slate-800 flex items-center gap-2"><BookOpen className="w-5 h-5 text-emerald-500"/> Subject Knowledge Base</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              Upload textbook chapters, marking schemes, or past papers here. The AI will ingest these files, build a semantic knowledge graph for this subject, and automatically use them to evaluate student submissions.
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
        </div>
      )}
    </div>
  );
};


// --- LAYER 3: ASSIGNMENT UPLOAD ZONE ---
const AssignmentUploadView: React.FC<{ subject: Subject, assignment: Assignment, onTutorial: () => void }> = ({ subject, assignment, onTutorial }) => {
  const [uploadMode, setUploadMode] = useState<"single"|"batch">("single");

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
  const [stagedStudents, setStagedStudents] = useState<StagedStudent[]>([]);
  const [pollIntervalId, setPollIntervalId] = useState<NodeJS.Timeout | null>(null);
  const [gradingProgress, setGradingProgress] = useState<any>(null);

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

      setSuccessMsg(`Submission for ${studentName} queued for grading!`);
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

      const token = await auth.currentUser?.getIdToken();
      if (!token) throw new Error("Authentication failed");

      const res = await fetch(`${API_URL}/api/instructor/batch`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`
        },
        body: fd
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Batch staging failed.");
      }

      const resData = await res.json();
      setBatchId(resData.batchId);
      setStagedStudents(resData.nameReviewList.map((item: any) => ({
        submissionId: item.submissionId,
        fileName: item.fileName,
        extractedName: item.extractedName || "Unknown"
      })));
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
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/instructor/batch/${id}`);
        setGradingProgress(res.data);
        if (res.data.status === "completed" || res.data.status === "failed") {
          clearInterval(interval); setPollIntervalId(null);
        }
      } catch (err) {}
    }, 3000);
    setPollIntervalId(interval);
  };

  useEffect(() => {
    return () => { if(pollIntervalId) clearInterval(pollIntervalId); };
  }, [pollIntervalId]);

  return (
    <div className="space-y-6">
      
      {/* Current Assignment Context */}
      <div className="glass-panel p-6 rounded-3xl border border-slate-200 bg-slate-50 flex justify-between items-center">
        <div>
           <h3 className="text-xl font-black text-slate-800">{assignment.title}</h3>
           <p className="text-xs text-slate-500 line-clamp-1 max-w-2xl mt-1"><span className="font-bold">Prompt:</span> {assignment.prompt}</p>
        </div>
        <button onClick={onTutorial} className="text-xs font-bold text-slate-400 hover:text-indigo-500 bg-white border border-slate-200 px-3 py-1.5 rounded-full flex items-center gap-1.5 shadow-sm">
          <HelpCircle className="w-3.5 h-3.5"/> Batch Tutorial
        </button>
      </div>

      <div className="flex gap-4">
         <button onClick={()=>setUploadMode("single")} className={`flex-1 py-4 rounded-2xl border-2 font-bold text-sm transition-all ${uploadMode === "single" ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"}`}>
            Single Submission Upload
         </button>
         <button onClick={()=>setUploadMode("batch")} className={`flex-1 py-4 rounded-2xl border-2 font-bold text-sm transition-all ${uploadMode === "batch" ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"}`}>
            Classroom Batch (Master ZIP)
         </button>
      </div>

      {error && <div className="p-4 rounded-xl bg-rose-50 text-rose-600 text-xs font-semibold">{error}</div>}
      {successMsg && <div className="p-4 rounded-xl bg-emerald-50 text-emerald-600 text-xs font-semibold">{successMsg}</div>}

      {gradingProgress && (
         <div className="glass-panel p-8 rounded-3xl border border-slate-200 shadow-lg space-y-6 bg-white">
            <h3 className="text-lg font-black text-slate-800">Batch Grading Progress: {gradingProgress.status}</h3>
            <div className="w-full bg-slate-100 h-3.5 rounded-full overflow-hidden border border-slate-200">
               <div className="bg-gradient-to-r from-indigo-600 to-emerald-500 h-full transition-all" style={{width: `${(gradingProgress.processedFiles / gradingProgress.totalFiles) * 100}%`}} />
            </div>
            {gradingProgress.status === "completed" && (
              <div className="flex gap-4 pt-4 border-t border-slate-100">
                <a href={gradingProgress.exportExcelUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 bg-emerald-600 text-white px-4 py-2 rounded-xl text-xs font-bold"><FileSpreadsheet className="w-4 h-4"/> Excel Report</a>
                <a href={gradingProgress.exportZipUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-xl text-xs font-bold"><FileArchive className="w-4 h-4"/> PDF Summaries</a>
                <button onClick={()=>setGradingProgress(null)} className="ml-auto text-xs font-bold text-slate-400">Clear</button>
              </div>
            )}
         </div>
      )}

      {/* SINGLE UPLOAD FORM */}
      {uploadMode === "single" && !gradingProgress && (
        <form onSubmit={handleSingleUpload} className="glass-panel p-8 rounded-3xl border border-slate-200 shadow-sm bg-white space-y-6">
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
        <div className="glass-panel p-8 rounded-3xl border border-slate-200 shadow-sm bg-white space-y-6">
          
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
    </div>
  );
};
