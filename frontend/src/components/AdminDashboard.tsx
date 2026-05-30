"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  Shield, Check, X, ShieldAlert,
  History, Users, Loader2, RefreshCw,
  GraduationCap, Landmark, UserCircle2, AlertTriangle,
  BadgeCheck, Clock, ExternalLink,
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
  createdAt: string;
}

interface WarningAlert {
  id: string;
  userId: string;
  submissionId: string | null;
  reason: string;
  severity: string;
  status: string;
  createdAt: string;
}

interface UserRow {
  uid: string;
  email: string;
  displayName: string;
  role: string;
  facultyStatus: string;
  proStatus: string;
  warningCount: number;
  createdAt: string;
}

interface AuditLog {
  id: string;
  actorId: string;
  action: string;
  target: string;
  timestamp: string;
  details: string;
}

const SEVERITY_BADGE: Record<string, string> = {
  low: "bg-yellow-50 text-yellow-700 border-yellow-200",
  medium: "bg-orange-50 text-orange-700 border-orange-200",
  high: "bg-red-50 text-red-700 border-red-200",
};

const ROLE_BADGE: Record<string, string> = {
  admin: "bg-rose-50 text-rose-700 border-rose-200",
  instructor: "bg-green-50 text-green-700 border-green-200",
  student: "bg-blue-50 text-blue-700 border-blue-200",
};

export const AdminDashboard: React.FC = () => {
  const { user } = useAuth();

  const [apps, setApps] = useState<FacultyApplication[]>([]);
  const [warnings, setWarnings] = useState<WarningAlert[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchAdminData = async () => {
    setLoading(true);
    setError(null);

    const [appsRes, warningsRes, auditRes, usersRes] = await Promise.allSettled([
      api.get("/api/admin/faculty-applications"),
      api.get("/api/admin/warnings"),
      api.get("/api/admin/audit-logs"),
      api.get("/api/admin/users"),
    ]);

    if (appsRes.status === "fulfilled") {
      setApps(Array.isArray(appsRes.value.data) ? appsRes.value.data : []);
    } else {
      console.error("Failed to load faculty applications:", appsRes.reason);
      setError("Failed to connect to the server. Ensure the backend is running and you have admin privileges.");
    }

    if (warningsRes.status === "fulfilled") {
      setWarnings(Array.isArray(warningsRes.value.data) ? warningsRes.value.data : []);
    } else {
      console.error("Failed to load warnings:", warningsRes.reason);
    }

    if (auditRes.status === "fulfilled") {
      setAuditLogs(Array.isArray(auditRes.value.data) ? auditRes.value.data : []);
    } else {
      console.error("Failed to load audit logs:", auditRes.reason);
    }

    if (usersRes.status === "fulfilled") {
      setUsers(Array.isArray(usersRes.value.data) ? usersRes.value.data : []);
    } else {
      console.error("Failed to load users:", usersRes.reason);
    }

    setLoading(false);
  };

  useEffect(() => {
    fetchAdminData();
  }, [user]);

  const handleApproveApp = async (id: string) => {
    try {
      await api.post(`/api/admin/faculty-applications/${id}/approve`);
      setSuccessMsg("Faculty verification granted. User upgraded to Instructor.");
      setTimeout(() => setSuccessMsg(null), 4000);
      fetchAdminData();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to approve application.");
    }
  };

  const handleRejectApp = async (id: string) => {
    const reason = prompt("Reason for rejection (shown to applicant):");
    if (!reason?.trim()) return;
    try {
      await api.post(`/api/admin/faculty-applications/${id}/reject`, { reason });
      setSuccessMsg("Application rejected.");
      setTimeout(() => setSuccessMsg(null), 4000);
      fetchAdminData();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to reject application.");
    }
  };

  const handleDismissWarning = async (id: string) => {
    try {
      await api.post(`/api/admin/warnings/${id}/dismiss`);
      setSuccessMsg("Warning dismissed and user counter decremented.");
      setTimeout(() => setSuccessMsg(null), 4000);
      fetchAdminData();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to dismiss warning.");
    }
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-[#eae7e1]">
        <div>
          <h2 className="text-base font-bold text-[#1c1c18] font-display flex items-center gap-2">
            <Shield className="w-4 h-4 text-red-600" />
            Administrative Control Panel
          </h2>
          <p className="text-xs text-[#8e8b80] mt-0.5">
            Oversee faculty status upgrades, clear compliance warnings, and audit security events.
          </p>
        </div>
        <button
          onClick={fetchAdminData}
          disabled={loading}
          className="flex items-center gap-1.5 text-[10px] font-bold text-[#5e5c54] hover:text-[#1c1c18] border border-[#dfdbd3] py-1.5 px-3 rounded-lg cursor-pointer transition-colors"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Banners */}
      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200">
          <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
          <p className="text-xs text-red-700">{error}</p>
        </div>
      )}
      {successMsg && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-green-50 border border-green-200">
          <BadgeCheck className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
          <p className="text-xs text-green-700">{successMsg}</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-xs text-[#8e8b80] py-4">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading admin data...
        </div>
      )}

      {/* ---- Stats Row ---- */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Total Users", value: users.length, icon: <Users className="w-4 h-4" />, color: "text-blue-700 bg-blue-50 border-blue-200" },
          { label: "Pending Applications", value: apps.length, icon: <Clock className="w-4 h-4" />, color: "text-amber-700 bg-amber-50 border-amber-200" },
          { label: "Active Warnings", value: warnings.length, icon: <ShieldAlert className="w-4 h-4" />, color: "text-red-700 bg-red-50 border-red-200" },
          { label: "Audit Events", value: auditLogs.length, icon: <History className="w-4 h-4" />, color: "text-green-700 bg-green-50 border-green-200" },
        ].map((stat) => (
          <div key={stat.label} className={`dev-card p-4 border rounded-xl flex items-center gap-3 ${stat.color}`}>
            {stat.icon}
            <div>
              <p className="text-xl font-black">{stat.value}</p>
              <p className="text-[10px] font-semibold opacity-80">{stat.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* ---- Pending Faculty Verifications ---- */}
      <div className="dev-card p-5 space-y-4">
        <h3 className="text-sm font-bold text-[#1c1c18] flex items-center gap-2">
          <Landmark className="w-4 h-4 text-amber-600" />
          Pending Faculty Verifications
          {apps.length > 0 && (
            <span className="ml-1 text-[9px] font-black px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">
              {apps.length}
            </span>
          )}
        </h3>

        {apps.length === 0 ? (
          <p className="text-xs text-[#8e8b80] italic py-3 text-center">No pending faculty registration applications.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-[#eae7e1]">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="bg-[#f5f3ef] border-b border-[#eae7e1] text-[#5e5c54] font-bold text-[10px] uppercase tracking-wider">
                  <th className="py-3 px-4">Name</th>
                  <th className="py-3 px-4">University / Dept</th>
                  <th className="py-3 px-4">Designation</th>
                  <th className="py-3 px-4">Official Email</th>
                  <th className="py-3 px-4">Proof</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#eae7e1]">
                {apps.map((app) => (
                  <tr key={app.id} className="hover:bg-[#f9f8f5] transition-colors">
                    <td className="py-3 px-4 font-bold text-[#1c1c18]">{app.fullName}</td>
                    <td className="py-3 px-4 text-[#5e5c54]">{app.university}{app.department ? ` · ${app.department}` : ""}</td>
                    <td className="py-3 px-4 text-[#5e5c54]">{app.designation || "—"}</td>
                    <td className="py-3 px-4 text-blue-700 font-semibold">{app.officialEmail}</td>
                    <td className="py-3 px-4">
                      {app.proofFileUrl ? (
                        <a href={app.proofFileUrl} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 text-[10px] font-bold text-blue-600 hover:underline">
                          <ExternalLink className="w-3 h-3" /> View
                        </a>
                      ) : (
                        <span className="text-[#8e8b80] text-[10px]">None</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          onClick={() => handleApproveApp(app.id)}
                          className="flex items-center gap-1 py-1 px-2.5 rounded-lg bg-green-50 text-green-700 border border-green-200 text-[10px] font-bold hover:bg-green-100 transition-colors cursor-pointer"
                          title="Approve"
                        >
                          <Check className="w-3 h-3" /> Approve
                        </button>
                        <button
                          onClick={() => handleRejectApp(app.id)}
                          className="flex items-center gap-1 py-1 px-2.5 rounded-lg bg-red-50 text-red-700 border border-red-200 text-[10px] font-bold hover:bg-red-100 transition-colors cursor-pointer"
                          title="Reject"
                        >
                          <X className="w-3 h-3" /> Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ---- Users Registry ---- */}
      <div className="dev-card p-5 space-y-4">
        <h3 className="text-sm font-bold text-[#1c1c18] flex items-center gap-2">
          <UserCircle2 className="w-4 h-4 text-blue-600" />
          User Registry
          <span className="ml-1 text-[9px] font-black px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
            {users.length}
          </span>
        </h3>

        {users.length === 0 ? (
          <p className="text-xs text-[#8e8b80] italic py-3 text-center">No users registered yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-[#eae7e1]">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="bg-[#f5f3ef] border-b border-[#eae7e1] text-[#5e5c54] font-bold text-[10px] uppercase tracking-wider">
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Role</th>
                  <th className="py-3 px-4">Faculty Status</th>
                  <th className="py-3 px-4">Warnings</th>
                  <th className="py-3 px-4">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#eae7e1]">
                {users.map((u) => (
                  <tr key={u.uid} className="hover:bg-[#f9f8f5] transition-colors">
                    <td className="py-3 px-4">
                      <p className="font-bold text-[#1c1c18]">{u.displayName || "—"}</p>
                      <p className="text-[10px] text-[#8e8b80] font-mono">{u.email}</p>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${ROLE_BADGE[u.role] || "bg-gray-50 text-gray-600 border-gray-200"}`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {u.facultyStatus !== "none" ? (
                        <span className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
                          {u.facultyStatus}
                        </span>
                      ) : (
                        <span className="text-[10px] text-[#8e8b80]">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {u.warningCount > 0 ? (
                        <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200">
                          {u.warningCount}
                        </span>
                      ) : (
                        <span className="text-[10px] text-[#8e8b80]">0</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-[10px] text-[#8e8b80] font-mono">
                      {new Date(u.createdAt).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ---- Bottom Row: Warnings + Audit ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Compliance Warnings */}
        <div className="dev-card p-5 space-y-3">
          <h3 className="text-sm font-bold text-[#1c1c18] flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-red-500" />
            Academic Compliance Warnings
          </h3>
          {warnings.length === 0 ? (
            <p className="text-xs text-[#8e8b80] italic py-3 text-center">No active compliance warnings.</p>
          ) : (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {warnings.map((warn) => (
                <div key={warn.id} className="p-3 rounded-xl border border-[#eae7e1] bg-[#fafaf8] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${SEVERITY_BADGE[warn.severity] || "bg-gray-50 text-gray-600 border-gray-200"}`}>
                      {warn.severity}
                    </span>
                    <span className="text-[10px] text-[#8e8b80]">{new Date(warn.createdAt).toLocaleString()}</span>
                  </div>
                  <p className="text-xs text-[#1c1c18] leading-relaxed">{warn.reason}</p>
                  <div className="flex items-center justify-between pt-1 border-t border-[#eae7e1]">
                    <span className="text-[9px] text-[#8e8b80] font-mono">User: {warn.userId.slice(0, 12)}…</span>
                    <button
                      onClick={() => handleDismissWarning(warn.id)}
                      className="flex items-center gap-1 text-[10px] font-bold text-green-700 hover:text-green-800 cursor-pointer"
                    >
                      <Check className="w-3 h-3" /> Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Security Audit Logger */}
        <div className="dev-card p-5 space-y-3">
          <h3 className="text-sm font-bold text-[#1c1c18] flex items-center gap-2">
            <History className="w-4 h-4 text-indigo-500" />
            Security Audit Logger
          </h3>
          {auditLogs.length === 0 ? (
            <p className="text-xs text-[#8e8b80] italic py-3 text-center">No audit events recorded yet.</p>
          ) : (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {auditLogs.map((log) => (
                <div key={log.id} className="p-3 rounded-xl bg-[#f5f3ef] border border-[#eae7e1] space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black text-indigo-700 uppercase tracking-wider">{log.action}</span>
                    <span className="text-[9px] text-[#8e8b80]">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <p className="text-[10px] text-[#5e5c54] italic">{log.details}</p>
                  <p className="text-[9px] text-[#8e8b80] font-mono">Actor: {log.actorId.slice(0, 12)}…</p>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
