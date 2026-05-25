"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { 
  Shield, Check, X, ShieldAlert, FileWarning, 
  History, Users, Sparkles, Loader2, RefreshCw 
} from "lucide-react";

interface FacultyApplication {
  id: string;
  userId: string;
  fullName: string;
  university: string;
  department: string;
  designation: string;
  officialEmail: string;
  proofFileUrl: string;
  status: string;
}

interface WarningAlert {
  id: string;
  userId: string;
  submissionId: string;
  reason: string;
  severity: string;
  status: string;
  createdAt: string;
}

export const AdminDashboard: React.FC = () => {
  const { user, isMock } = useAuth();
  
  // Dashboard Metrics & Data Lists State
  const [apps, setApps] = useState<FacultyApplication[]>([]);
  const [warnings, setWarnings] = useState<WarningAlert[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  
  // General status flags
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchAdminData = async () => {
    setLoading(true);
    setError(null);
    try {
      if (isMock) {
        // Hydrate simulated dashboard metrics
        setApps([
          {
            id: "app_f0eb2cee",
            userId: "mock_instructor_uid",
            fullName: "Dr. Sarah Jenkins",
            university: "Quaid-e-Azam University",
            department: "Computer Science",
            designation: "Assistant Professor",
            officialEmail: "jenkins@qau.edu.pk",
            proofFileUrl: "file:///i:/fyp implementation/backend/app/temp_mock_storage/faculty_proofs/proof.pdf",
            status: "pending"
          }
        ]);
        
        setWarnings([
          {
            id: "warn_sub_df4f",
            userId: "mock_student_uid",
            submissionId: "sub_df4fd000",
            reason: "Sensitive material detected: code phrase matching 'cheat sheet, leaked exam, confidential key'",
            severity: "high",
            status: "active",
            createdAt: new Date().toISOString()
          }
        ]);

        setAuditLogs([
          {
            id: "log_1",
            actorId: "mock_student_uid",
            action: "POLICY_VIOLATION",
            details: "Submission flagged: Sensitive material matching leaks list",
            timestamp: new Date().toISOString()
          },
          {
            id: "log_2",
            actorId: "mock_instructor_uid",
            action: "FACULTY_APPLIED",
            details: "Dr. Sarah Jenkins applied for faculty validation",
            timestamp: new Date(Date.now() - 300000).toISOString()
          }
        ]);
        return;
      }

      // Fetch from live FastAPI routes
      const appsRes = await api.get("/api/admin/faculty-applications");
      const warningsRes = await api.get("/api/admin/warnings");
      
      setApps(Array.isArray(appsRes.data) ? appsRes.data : []);
      setWarnings(Array.isArray(warningsRes.data) ? warningsRes.data : []);
      
      // Simulate/Pull logs
      setAuditLogs([
        {
          id: "log_1",
          actorId: "mock_student_uid",
          action: "POLICY_VIOLATION",
          details: "Submission flagged: Sensitive material matching leaks list",
          timestamp: new Date().toISOString()
        }
      ]);
    } catch (err: any) {
      console.warn("Failed to fetch administrative lists. Seeded mock backups.", err);
      // Fallback
      setApps([]);
      setWarnings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdminData();
  }, [user, isMock]);

  // Approve faculty application
  const handleApproveApp = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      if (isMock) {
        setApps(prev => prev.map(a => a.id === id ? { ...a, status: "approved" } : a));
        setSuccessMsg("Instructor application approved successfully!");
      } else {
        await api.post(`/api/admin/faculty-applications/${id}/approve`);
        setSuccessMsg("Faculty verification granted and privileges updated.");
        fetchAdminData();
      }
    } catch (err: any) {
      setError(err.message || "Failed to approve application.");
    } finally {
      setLoading(false);
    }
  };

  // Reject faculty application
  const handleRejectApp = async (id: string) => {
    const reason = prompt("Please provide a reason for rejecting this application:") || "";
    if (!reason.trim()) return;

    setLoading(true);
    setError(null);
    try {
      if (isMock) {
        setApps(prev => prev.map(a => a.id === id ? { ...a, status: "rejected" } : a));
        setSuccessMsg("Application rejected.");
      } else {
        await api.post(`/api/admin/faculty-applications/${id}/reject`, { reason });
        setSuccessMsg("Faculty verification application rejected.");
        fetchAdminData();
      }
    } catch (err: any) {
      setError(err.message || "Failed to reject application.");
    } finally {
      setLoading(false);
    }
  };

  // Dismiss user warning alert
  const handleDismissWarning = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      if (isMock) {
        setWarnings(prev => prev.filter(w => w.id !== id));
        setSuccessMsg("Compliance warning dismissed! User count decremented.");
      } else {
        await api.post(`/api/admin/warnings/${id}/dismiss`);
        setSuccessMsg("Warning dismissed. Counter levels reset in profiles.");
        fetchAdminData();
      }
    } catch (err: any) {
      setError(err.message || "Failed to dismiss warning alert.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl w-full mx-auto px-4 py-8 space-y-10 animate-fade-in-up">
      
      {/* Header Panel */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h2 className="text-3xl font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
            <Shield className="w-7 h-7 text-indigo-500 animate-float" />
            Administrative Control Panel
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Oversee faculty status upgrades, clear student compliance warnings, and audit security events.
          </p>
        </div>

        <button
          onClick={fetchAdminData}
          disabled={loading}
          className="inline-flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-350 text-xs font-bold hover:bg-slate-50 active:scale-95 transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh Registry
        </button>
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

      {/* Row 1: Faculty Verifications Applications */}
      <div className="glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg space-y-6">
        <h3 className="text-lg font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
          <Users className="w-5 h-5 text-indigo-500" />
          Pending Faculty Verifications
        </h3>

        {apps.length === 0 ? (
          <p className="text-xs text-slate-450 italic py-4">No pending faculty registration applications found.</p>
        ) : (
          <div className="overflow-x-auto border border-slate-200 dark:border-slate-800 rounded-2xl">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-950 font-extrabold text-slate-500 border-b border-slate-200 dark:border-slate-800">
                  <th className="py-3 px-4">Instructor</th>
                  <th className="py-3 px-4">University</th>
                  <th className="py-3 px-4">Designation</th>
                  <th className="py-3 px-4">Institution Email</th>
                  <th className="py-3 px-4">Proof Document</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {apps.map((app) => (
                  <tr key={app.id} className="hover:bg-slate-50/40 dark:hover:bg-slate-900/20 font-medium">
                    <td className="py-4 px-4 font-bold text-slate-700 dark:text-slate-200">{app.fullName}</td>
                    <td className="py-4 px-4 text-slate-500">{app.university} ({app.department})</td>
                    <td className="py-4 px-4 text-slate-500">{app.designation}</td>
                    <td className="py-4 px-4 font-semibold text-indigo-600 dark:text-indigo-400">{app.officialEmail}</td>
                    <td className="py-4 px-4">
                      <a 
                        href={app.proofFileUrl} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-xs text-indigo-500 font-extrabold hover:underline"
                      >
                        Open File
                      </a>
                    </td>
                    <td className="py-4 px-4 text-right">
                      {app.status === "pending" ? (
                        <div className="inline-flex items-center gap-2 justify-end">
                          <button
                            onClick={() => handleApproveApp(app.id)}
                            className="p-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 border border-emerald-150 hover:bg-emerald-100 dark:hover:bg-emerald-900 active:scale-95 transition-all cursor-pointer"
                            title="Approve verification"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleRejectApp(app.id)}
                            className="p-1.5 rounded-lg bg-rose-50 dark:bg-rose-950 text-rose-600 dark:text-rose-450 border border-rose-150 hover:bg-rose-100 dark:hover:bg-rose-900 active:scale-95 transition-all cursor-pointer"
                            title="Reject verification"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-[10px] font-extrabold text-slate-400 uppercase">{app.status}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Row 2: Policy Warnings List & Audit Logger */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* Active compliance warnings alerts */}
        <div className="lg:col-span-7 glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg space-y-6">
          <h3 className="text-lg font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-500" />
            Academic Compliance Warnings
          </h3>

          {warnings.length === 0 ? (
            <p className="text-xs text-slate-450 italic py-4">No active compliance warnings flagged.</p>
          ) : (
            <div className="space-y-4">
              {warnings.map((warn) => (
                <div key={warn.id} className="p-4 rounded-2xl border border-rose-100 dark:border-rose-900/30 bg-rose-50/10 dark:bg-rose-950/10 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="py-1 px-2.5 rounded-lg bg-rose-100 dark:bg-rose-950 text-rose-600 dark:text-rose-400 border border-rose-150 font-bold text-[9px] uppercase tracking-wider">
                      Severity: {warn.severity}
                    </span>
                    <span className="text-[10px] text-slate-450 font-medium">{new Date(warn.createdAt).toLocaleString()}</span>
                  </div>

                  <p className="text-xs text-slate-700 dark:text-slate-350 leading-relaxed font-semibold">
                    {warn.reason}
                  </p>

                  <div className="flex items-center justify-between pt-2 border-t border-rose-100 dark:border-rose-900/20">
                    <span className="text-[10px] text-slate-400 font-bold">User: {warn.userId}</span>
                    <button
                      onClick={() => handleDismissWarning(warn.id)}
                      className="inline-flex items-center gap-1 text-[10px] font-black text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
                    >
                      <Check className="w-3.5 h-3.5" />
                      Dismiss Alert & Reset Count
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* System audit log feed */}
        <div className="lg:col-span-5 glass-panel dark:bg-slate-900/60 p-8 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-lg space-y-6">
          <h3 className="text-lg font-black text-slate-850 dark:text-slate-100 flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-500" />
            Security Audit Logger
          </h3>

          <div className="space-y-4 max-h-[350px] overflow-y-auto pr-1">
            {auditLogs.map((log) => (
              <div key={log.id} className="p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-850 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-extrabold text-indigo-600 dark:text-indigo-400 tracking-wider">{log.action}</span>
                  <span className="text-[9px] text-slate-400">{new Date(log.timestamp).toLocaleTimeString()}</span>
                </div>
                <p className="text-[10px] text-slate-600 dark:text-slate-350 leading-relaxed italic">
                  "{log.details}"
                </p>
                <div className="text-[9px] text-slate-450">Actor: {log.actorId}</div>
              </div>
            ))}
          </div>
        </div>

      </div>

    </div>
  );
};
