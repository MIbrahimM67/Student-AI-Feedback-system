"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  Shield, Check, X, ShieldAlert,
  History, Users, Loader2, RefreshCw,
  GraduationCap, Landmark, UserCircle2, AlertTriangle,
  BadgeCheck, Clock, ExternalLink, Search,
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
  const [usersError, setUsersError] = useState(false);
  const [appsError, setAppsError] = useState(false);
  const [warningsError, setWarningsError] = useState(false);
  const [auditError, setAuditError] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [sortOrder, setSortOrder] = useState("newest");

  const visibleUsers = React.useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return users
      .filter((u) => (roleFilter === "all" || u.role === roleFilter) &&
        (!query || `${u.displayName} ${u.email}`.toLowerCase().includes(query)))
      .sort((a, b) => sortOrder === "newest"
        ? new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        : new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  }, [users, searchTerm, roleFilter, sortOrder]);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchAdminData = async () => {
    setLoading(true);
    setError(null);
    setUsersError(false);
    setAppsError(false);
    setWarningsError(false);
    setAuditError(false);

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
      setApps([]);
      setAppsError(true);
      setError("Faculty applications could not be loaded. Check the connection and admin access.");
    }

    if (warningsRes.status === "fulfilled") {
      setWarnings(Array.isArray(warningsRes.value.data) ? warningsRes.value.data : []);
    } else {
      console.error("Failed to load warnings:", warningsRes.reason);
      setWarnings([]);
      setWarningsError(true);
    }

    if (auditRes.status === "fulfilled") {
      setAuditLogs(Array.isArray(auditRes.value.data) ? auditRes.value.data : []);
    } else {
      console.error("Failed to load audit logs:", auditRes.reason);
      setAuditLogs([]);
      setAuditError(true);
    }

    if (usersRes.status === "fulfilled") {
      setUsers(Array.isArray(usersRes.value.data) ? usersRes.value.data : []);
    } else {
      console.error("Failed to load users:", usersRes.reason);
      setUsers([]);
      setUsersError(true);
    }

    if (warningsRes.status === "rejected" || auditRes.status === "rejected") {
      setError("Some admin data could not be refreshed. Try again.");
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

  const handleInstructorAccess = async (target: UserRow) => {
    if (target.role === "admin") return;
    const nextRole = target.role === "instructor" ? "student" : "instructor";
    const action = nextRole === "instructor" ? "grant instructor access to" : "revoke instructor access from";
    if (!window.confirm(`Do you want to ${action} ${target.email}?`)) return;
    try {
      await api.patch(`/api/admin/users/${encodeURIComponent(target.uid)}/role`, { role: nextRole });
      setSuccessMsg(`Instructor access ${nextRole === "instructor" ? "granted" : "revoked"} for ${target.email}.`);
      setTimeout(() => setSuccessMsg(null), 4000);
      fetchAdminData();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Could not update instructor access.");
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
          { label: "Total Users", value: usersError ? "—" : users.length, icon: <Users className="w-4 h-4" />, color: "text-blue-700 bg-blue-50 border-blue-200" },
          { label: "Pending Applications", value: appsError ? "—" : apps.length, icon: <Clock className="w-4 h-4" />, color: "text-amber-700 bg-amber-50 border-amber-200" },
          { label: "Active Warnings", value: warningsError ? "—" : warnings.length, icon: <ShieldAlert className="w-4 h-4" />, color: "text-red-700 bg-red-50 border-red-200" },
          { label: "Audit Events", value: auditError ? "—" : auditLogs.length, icon: <History className="w-4 h-4" />, color: "text-green-700 bg-green-50 border-green-200" },
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

        {loading ? (
          <p className="py-3 text-sm text-[var(--color-muted)]">Loading applications…</p>
        ) : appsError ? (
          <p className="py-3 text-sm text-[var(--color-error)]">Faculty applications could not be loaded. Use Refresh to try again.</p>
        ) : apps.length === 0 ? (
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

      {/* ---- User Registry ---- */}
      <section className="dev-card min-w-0 p-4 sm:p-5 space-y-4" aria-labelledby="user-registry-title">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 id="user-registry-title" className="flex items-center gap-2 text-base font-bold text-[var(--color-ink)]">
              <UserCircle2 className="h-5 w-5 text-[var(--color-accent)]" />
              User registry
            </h3>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              Find an account and review its role, faculty verification and warnings.
            </p>
          </div>
          <span className="self-start rounded-full border border-[var(--color-rule)] px-2.5 py-1 text-[11px] font-semibold text-[var(--color-ink-2)]" aria-live="polite">
            {loading ? "Loading users…" : usersError ? "Unavailable" : `${visibleUsers.length} of ${users.length} users`}
          </span>
        </div>

        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_160px_160px]">
          <label className="relative block">
            <span className="sr-only">Search users by name or email</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]" />
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search name or email"
              className="h-11 w-full rounded-lg border border-[var(--color-rule)] bg-[var(--color-paper-2)] pl-10 pr-3 text-sm text-[var(--color-ink)]"
            />
          </label>
          <label>
            <span className="sr-only">Filter by role</span>
            <select
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value)}
              className="h-11 w-full rounded-lg border border-[var(--color-rule)] bg-[var(--color-paper-2)] px-3 text-xs text-[var(--color-ink)]"
            >
              <option value="all">All roles</option>
              <option value="admin">Admins</option>
              <option value="instructor">Instructors</option>
              <option value="student">Students</option>
            </select>
          </label>
          <label>
            <span className="sr-only">Sort users</span>
            <select
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
              className="h-11 w-full rounded-lg border border-[var(--color-rule)] bg-[var(--color-paper-2)] px-3 text-xs text-[var(--color-ink)]"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
        </div>

        {loading ? (
          <p className="flex items-center gap-2 py-6 text-sm text-[var(--color-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading user registry…
          </p>
        ) : usersError ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-rule)] p-4">
            <p className="text-sm text-[var(--color-error)]">The user registry could not be loaded.</p>
            <button onClick={fetchAdminData} className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-rule)] px-3 py-2 text-xs font-bold text-[var(--color-ink)] hover:bg-[var(--color-surface-2)]">
              <RefreshCw className="h-4 w-4" /> Retry
            </button>
          </div>
        ) : users.length === 0 ? (
          <p className="rounded-lg border border-[var(--color-rule)] p-5 text-sm text-[var(--color-muted)]">No users are registered yet.</p>
        ) : visibleUsers.length === 0 ? (
          <p className="rounded-lg border border-[var(--color-rule)] p-5 text-sm text-[var(--color-muted)]">No users match these filters.</p>
        ) : (
          <>
            <div className="hidden overflow-x-auto rounded-lg border border-[var(--color-rule)] md:block">
              <table className="w-full min-w-[760px] text-left text-xs">
                <thead className="border-b border-[var(--color-rule)] bg-[var(--color-paper-2)] text-[10px] font-bold uppercase tracking-wider text-[var(--color-muted)]">
                  <tr>
                    <th scope="col" className="px-4 py-3">User</th>
                    <th scope="col" className="px-4 py-3">Role</th>
                    <th scope="col" className="px-4 py-3">Faculty status</th>
                    <th scope="col" className="px-4 py-3">Warnings</th>
                    <th scope="col" className="px-4 py-3">Access</th>
                    <th scope="col" className="px-4 py-3">Joined</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-rule)]">
                  {visibleUsers.map((u) => (
                    <tr key={u.uid} className="hover:bg-[var(--color-surface-2)]">
                      <td className="max-w-[340px] px-4 py-3">
                        <p className="truncate text-sm font-bold text-[var(--color-ink)]">{u.displayName || "Unnamed user"}</p>
                        <p className="truncate text-[11px] text-[var(--color-muted)]" title={u.email}>{u.email || "No email"}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase ${ROLE_BADGE[u.role] || "bg-gray-50 text-gray-600 border-gray-200"}`}>{u.role || "unknown"}</span>
                      </td>
                      <td className="px-4 py-3 text-[11px] text-[var(--color-ink-2)]">
                        {u.facultyStatus && u.facultyStatus !== "none" ? u.facultyStatus : "—"}
                      </td>
                      <td className="px-4 py-3 font-semibold text-[var(--color-ink-2)]">{u.warningCount ?? 0}</td>
                      <td className="px-4 py-3">
                        {u.role === "admin" ? (
                          <span className="text-[11px] text-[var(--color-muted)]">Protected</span>
                        ) : (
                          <button type="button" onClick={() => handleInstructorAccess(u)}
                            className="rounded-lg border border-[var(--color-rule)] px-2.5 py-1.5 text-[11px] font-bold text-[var(--color-ink)] hover:bg-[#fff0a6] transition-colors">
                            {u.role === "instructor" ? "Revoke instructor" : "Grant instructor"}
                          </button>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-[11px] text-[var(--color-muted)]">
                        {new Date(u.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="grid gap-2 md:hidden">
              {visibleUsers.map((u) => (
                <article key={u.uid} className="min-w-0 rounded-lg border border-[var(--color-rule)] bg-[var(--color-paper-2)] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-bold text-[var(--color-ink)]">{u.displayName || "Unnamed user"}</p>
                      <p className="break-all text-xs text-[var(--color-muted)]">{u.email || "No email"}</p>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2 py-1 text-[9px] font-bold uppercase ${ROLE_BADGE[u.role] || "bg-gray-50 text-gray-600 border-gray-200"}`}>{u.role || "unknown"}</span>
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-[var(--color-rule)] pt-3 text-[11px]">
                    <div><dt className="text-[var(--color-muted)]">Faculty</dt><dd className="mt-1 text-[var(--color-ink-2)]">{u.facultyStatus && u.facultyStatus !== "none" ? u.facultyStatus : "—"}</dd></div>
                    <div><dt className="text-[var(--color-muted)]">Warnings</dt><dd className="mt-1 text-[var(--color-ink-2)]">{u.warningCount ?? 0}</dd></div>
                    <div><dt className="text-[var(--color-muted)]">Joined</dt><dd className="mt-1 text-[var(--color-ink-2)]">{new Date(u.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</dd></div>
                  </dl>
                  {u.role !== "admin" && (
                    <button type="button" onClick={() => handleInstructorAccess(u)}
                      className="mt-3 w-full rounded-lg border border-[var(--color-rule)] px-3 py-2 text-xs font-bold text-[var(--color-ink)] hover:bg-[#fff0a6] transition-colors">
                      {u.role === "instructor" ? "Revoke instructor" : "Grant instructor"}
                    </button>
                  )}
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      {/* ---- Bottom Row: Warnings + Audit ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Compliance Warnings */}
        <div className="dev-card p-5 space-y-3">
          <h3 className="text-sm font-bold text-[#1c1c18] flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-red-500" />
            Academic Compliance Warnings
          </h3>
          {loading ? (
            <p className="py-3 text-sm text-[var(--color-muted)]">Loading warnings…</p>
          ) : warningsError ? (
            <p className="py-3 text-sm text-[var(--color-error)]">Warnings could not be loaded. Use Refresh to try again.</p>
          ) : warnings.length === 0 ? (
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
          {loading ? (
            <p className="py-3 text-sm text-[var(--color-muted)]">Loading audit events…</p>
          ) : auditError ? (
            <p className="py-3 text-sm text-[var(--color-error)]">Audit events could not be loaded. Use Refresh to try again.</p>
          ) : auditLogs.length === 0 ? (
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
