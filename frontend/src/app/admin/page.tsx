"use client";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users, Briefcase, Zap, Activity, ShieldCheck, ShieldAlert,
  Loader2, Sparkles, RefreshCw, CheckCircle, AlertCircle, ArrowUpRight,
  UserCheck, UserX, Clock, Globe, ChevronRight, Building2, ExternalLink,
  Plus, Search, Trash2, Check, X, Filter
} from "lucide-react";
import { adminApi, companiesApi, TargetCompany } from "@/lib/api";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";

type TabType = "overview" | "users" | "jobs" | "matches" | "companies";

interface UserRecord {
  _id: string;
  discord_id: string;
  discord_username: string;
  discord_avatar?: string;
  email?: string;
  role: "user" | "admin";
  is_active: boolean;
  created_at?: string;
  last_login?: string;
}

interface RecentJob {
  _id: string;
  title: string;
  company: string;
  location?: string;
  is_remote?: boolean;
  source?: string;
  source_url?: string;
  discovered_at?: string;
}

interface RecentMatch {
  _id: string;
  user_id: string;
  compatibility_score: number;
  reasoning?: string;
  matching_skills?: string[];
  job: {
    _id: string;
    title: string;
    company: string;
    location?: string;
    is_remote?: boolean;
  };
}

export default function AdminPage() {
  const { user: currentUser } = useAuth();
  const [tab, setTab] = useState<TabType>("overview");
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [recentMatches, setRecentMatches] = useState<RecentMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [triggeringDiscovery, setTriggeringDiscovery] = useState(false);
  const [discoveryMsg, setDiscoveryMsg] = useState("");
  const [updatingUser, setUpdatingUser] = useState<string | null>(null);

  // ── Target Companies State ──
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [companyCounts, setCompanyCounts] = useState<{
    all: number;
    "Tier-1": number;
    "Tier-2": number;
    "Tier-3": number;
    Startup: number;
    active: number;
  }>({ all: 0, "Tier-1": 0, "Tier-2": 0, "Tier-3": 0, Startup: 0, active: 0 });
  const [selectedGrade, setSelectedGrade] = useState<string>("all");
  const [companySearch, setCompanySearch] = useState<string>("");
  const [loadingCompanies, setLoadingCompanies] = useState<boolean>(false);
  const [showAddCompanyModal, setShowAddCompanyModal] = useState<boolean>(false);
  const [savingCompany, setSavingCompany] = useState<boolean>(false);
  const [seedingCompanies, setSeedingCompanies] = useState<boolean>(false);
  const [companyActionMsg, setCompanyActionMsg] = useState<string>("");
  const [newCompany, setNewCompany] = useState({
    name: "",
    grade: "Tier-1",
    career_page: "",
    ats_type: "greenhouse",
    board_token: "",
    industry: "",
    location_hq: "",
    is_active: true,
  });

  const loadCompanies = async (grade = selectedGrade, search = companySearch) => {
    setLoadingCompanies(true);
    try {
      const res = await companiesApi.list({ grade, search });
      setCompanies(res.items || []);
      if (res.grade_counts) {
        setCompanyCounts(res.grade_counts);
      }
    } catch (err: unknown) {
      console.error("Failed to load target companies", err);
    } finally {
      setLoadingCompanies(false);
    }
  };

  const handleToggleCompany = async (comp: TargetCompany) => {
    try {
      await companiesApi.update(comp._id, { is_active: !comp.is_active });
      setCompanies((prev) =>
        prev.map((c) => (c._id === comp._id ? { ...c, is_active: !comp.is_active } : c))
      );
      setCompanyActionMsg(`${comp.name} status updated.`);
      setTimeout(() => setCompanyActionMsg(""), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to toggle company";
      alert(msg);
    }
  };

  const handleDeleteCompany = async (id: string, name: string) => {
    if (!confirm(`Delete ${name} from target companies?`)) return;
    try {
      await companiesApi.delete(id);
      setCompanies((prev) => prev.filter((c) => c._id !== id));
      loadCompanies(selectedGrade, companySearch);
      setCompanyActionMsg(`${name} removed.`);
      setTimeout(() => setCompanyActionMsg(""), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete company";
      alert(msg);
    }
  };

  const handleCreateCompany = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCompany.name.trim() || !newCompany.career_page.trim()) {
      alert("Company name and career page URL are required.");
      return;
    }
    setSavingCompany(true);
    try {
      await companiesApi.create(newCompany);
      setShowAddCompanyModal(false);
      setNewCompany({
        name: "",
        grade: "Tier-1",
        career_page: "",
        ats_type: "greenhouse",
        board_token: "",
        industry: "",
        location_hq: "",
        is_active: true,
      });
      setCompanyActionMsg("Company successfully added to MongoDB!");
      setTimeout(() => setCompanyActionMsg(""), 4000);
      loadCompanies(selectedGrade, companySearch);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create company";
      alert(msg);
    } finally {
      setSavingCompany(false);
    }
  };

  const handleSeedCompanies = async () => {
    if (!confirm("Re-sync default verified target companies list in MongoDB?")) return;
    setSeedingCompanies(true);
    try {
      const res = await companiesApi.seed(true);
      setCompanyActionMsg(res.message);
      setTimeout(() => setCompanyActionMsg(""), 4000);
      loadCompanies(selectedGrade, companySearch);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to seed companies";
      alert(msg);
    } finally {
      setSeedingCompanies(false);
    }
  };

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sRes, uRes, aRes] = await Promise.all([
        adminApi.stats(),
        adminApi.users().catch(() => ({ users: [] })),
        adminApi.activity().catch(() => ({ recent_jobs: [], recent_matches: [] })),
      ]);
      setStats(sRes);
      setUsers((uRes.users as UserRecord[]) || []);
      setRecentJobs((aRes.recent_jobs as RecentJob[]) || []);
      setRecentMatches((aRes.recent_matches as RecentMatch[]) || []);
      await loadCompanies();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load admin data";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (tab === "companies") {
      loadCompanies(selectedGrade, companySearch);
    }
  }, [tab, selectedGrade]);

  const handleToggleUserRole = async (targetUser: UserRecord) => {
    const nextRole = targetUser.role === "admin" ? "user" : "admin";
    setUpdatingUser(targetUser._id);
    try {
      await adminApi.updateUser(targetUser._id, { role: nextRole });
      setUsers((prev) =>
        prev.map((u) => (u._id === targetUser._id ? { ...u, role: nextRole } : u))
      );
    } catch (err) {
      console.error("Failed to update user role", err);
    } finally {
      setUpdatingUser(null);
    }
  };

  const handleTriggerDiscovery = async () => {
    setTriggeringDiscovery(true);
    setDiscoveryMsg("");
    try {
      const res = await adminApi.triggerDiscovery();
      setDiscoveryMsg(res.message || "Discovery triggered across all sources!");
      setTimeout(loadAll, 4000);
      setTimeout(() => {
        loadAll();
        setTriggeringDiscovery(false);
      }, 8000);
    } catch (err: unknown) {
      setDiscoveryMsg(err instanceof Error ? err.message : "Failed to trigger discovery");
      setTriggeringDiscovery(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
        <p className="text-xs text-slate-400">Loading admin operations…</p>
      </div>
    );
  }

  if (error && error.toLowerCase().includes("admin access required")) {
    return (
      <div className="p-4 sm:p-8 max-w-xl mx-auto my-12">
        <div className="glass rounded-3xl p-8 text-center border border-rose-500/20">
          <div className="w-14 h-14 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center mx-auto mb-4 text-rose-400">
            <ShieldAlert className="w-7 h-7" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Admin Access Required</h2>
          <p className="text-xs text-slate-400 leading-relaxed mb-6">
            Your current account does not have administrator privileges. Add your email address to the authorized admin list or sign in with an admin account.
          </p>
          <Link
            href="/user/dashboard"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold transition-all border border-white/10"
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const kpis = [
    {
      label: "Platform Users",
      value: stats?.users ?? 0,
      icon: Users,
      color: "from-blue-500/20 to-indigo-500/20 text-indigo-400 border-indigo-500/30",
    },
    {
      label: "Ingested Jobs",
      value: stats?.active_jobs ?? 0,
      icon: Briefcase,
      color: "from-emerald-500/20 to-teal-500/20 text-emerald-400 border-emerald-500/30",
    },
    {
      label: "Profile Matches",
      value: stats?.total_matches ?? 0,
      icon: Sparkles,
      color: "from-purple-500/20 to-pink-500/20 text-purple-400 border-purple-500/30",
    },
    {
      label: "Applications",
      value: stats?.total_applications ?? 0,
      icon: Zap,
      color: "from-yellow-500/20 to-amber-500/20 text-yellow-400 border-yellow-500/30",
    },
  ];

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-6xl">
      {/* ── Top Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1 rounded-md bg-purple-500/20 text-purple-400 border border-purple-500/30">
              <ShieldCheck className="w-4 h-4" />
            </span>
            <span className="text-[11px] font-bold text-purple-400 tracking-wider uppercase">System Administration</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text mt-1">Platform Control Center</h1>
          <p className="text-slate-500 text-xs mt-0.5">Manage users, monitor scraper pipelines, and inspect real-time platform operations</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold border border-white/10 transition-all cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
          <button
            onClick={handleTriggerDiscovery}
            disabled={triggeringDiscovery}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 cursor-pointer"
          >
            {triggeringDiscovery ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {triggeringDiscovery ? "Scraping & Matching…" : "Trigger Job Scraper"}
          </button>
        </div>
      </div>

      {discoveryMsg && (
        <div className="mb-6 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{discoveryMsg}</span>
        </div>
      )}

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {kpis.map(({ label, value, icon: Icon, color }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass rounded-2xl p-5 relative overflow-hidden"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{label}</span>
              <div className={`p-2 rounded-xl bg-gradient-to-br border ${color}`}>
                <Icon className="w-4 h-4" />
              </div>
            </div>
            <p className="text-3xl font-black text-white">{String(value ?? 0)}</p>
          </motion.div>
        ))}
      </div>

      {/* ── Navigation Tabs ── */}
      <div className="flex items-center gap-2 border-b border-white/10 pb-3 mb-6">
        <button
          onClick={() => setTab("overview")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            tab === "overview"
              ? "bg-white/10 text-white border border-white/15"
              : "text-slate-400 hover:text-white hover:bg-white/5"
          }`}
        >
          Overview & Status
        </button>
        <button
          onClick={() => setTab("users")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
            tab === "users"
              ? "bg-white/10 text-white border border-white/15"
              : "text-slate-400 hover:text-white hover:bg-white/5"
          }`}
        >
          Users Directory
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-white/10">{users.length}</span>
        </button>
        <button
          onClick={() => setTab("jobs")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
            tab === "jobs"
              ? "bg-white/10 text-white border border-white/15"
              : "text-slate-400 hover:text-white hover:bg-white/5"
          }`}
        >
          Recent Ingested Jobs
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-white/10">{recentJobs.length}</span>
        </button>
        <button
          onClick={() => setTab("matches")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
            tab === "matches"
              ? "bg-white/10 text-white border border-white/15"
              : "text-slate-400 hover:text-white hover:bg-white/5"
          }`}
        >
          Candidate Matches
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-white/10">{recentMatches.length}</span>
        </button>
        <button
          onClick={() => setTab("companies")}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
            tab === "companies"
              ? "bg-purple-600/20 text-purple-200 border border-purple-500/30"
              : "text-slate-400 hover:text-white hover:bg-white/5"
          }`}
        >
          <Building2 className="w-3.5 h-3.5 text-purple-400" />
          Target Companies
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-purple-500/20 text-purple-300 font-bold">
            {companyCounts.all || companies.length}
          </span>
        </button>
      </div>

      {/* ── Tab Content ── */}
      <AnimatePresence mode="wait">
        {tab === "overview" && (
          <motion.div
            key="overview"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-6"
          >
            {/* Application Status Breakdown */}
            <div className="glass rounded-2xl p-6">
              <h2 className="font-bold text-sm text-white mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-indigo-400" />
                Application Pipeline Breakdown
              </h2>
              {stats?.application_status_breakdown &&
              Object.keys(stats.application_status_breakdown as object).length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {Object.entries((stats?.application_status_breakdown as Record<string, number>) ?? {}).map(
                    ([st, count]) => (
                      <div
                        key={st}
                        className="rounded-xl p-3.5 bg-white/[0.02] border border-white/5"
                      >
                        <p className="text-2xl font-black text-white">{count}</p>
                        <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-wider font-semibold">
                          {st.replace(/_/g, " ")}
                        </p>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <div className="py-8 text-center text-xs text-slate-500 bg-white/[0.01] rounded-xl border border-white/5">
                  No applications submitted yet. Jobs will appear here as users or auto-apply agents submit resumes.
                </div>
              )}
            </div>

            {/* Ingestion & Match Summary */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div className="glass rounded-2xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <Briefcase className="w-3.5 h-3.5 text-emerald-400" /> Job Scraper Status
                  </h3>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
                    Healthy
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Default source feeds configured: <strong>RemoteOK API</strong>, <strong>Hacker News Career Listings</strong>. Content hashes prevent duplicate entries across scrape cycles.
                </p>
                <div className="pt-2 flex items-center justify-between text-xs text-slate-400 border-t border-white/5">
                  <span>Total Parsed Postings:</span>
                  <span className="font-bold text-white">{String(stats?.active_jobs ?? 0)} jobs</span>
                </div>
              </div>

              <div className="glass rounded-2xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" /> AI Matcher Engine
                  </h3>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20 font-semibold">
                    Ollama / LLM
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Matches candidates against required skills, remote preferences, and job titles. Scores above 60% are ranked and surfaced on the candidate dashboard.
                </p>
                <div className="pt-2 flex items-center justify-between text-xs text-slate-400 border-t border-white/5">
                  <span>Computed Matches:</span>
                  <span className="font-bold text-white">{String(stats?.total_matches ?? 0)} matches</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {tab === "users" && (
          <motion.div
            key="users"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass rounded-2xl overflow-hidden"
          >
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h2 className="font-bold text-sm text-white">Registered Users Directory</h2>
              <span className="text-xs text-slate-400">{users.length} total users</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/5 text-slate-400 bg-white/[0.01]">
                    <th className="py-3 px-4 font-semibold">User</th>
                    <th className="py-3 px-4 font-semibold">Email</th>
                    <th className="py-3 px-4 font-semibold">Role</th>
                    <th className="py-3 px-4 font-semibold">Status</th>
                    <th className="py-3 px-4 font-semibold">Last Active</th>
                    <th className="py-3 px-4 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {users.map((u) => {
                    const avatar = u.discord_avatar
                      ? `https://cdn.discordapp.com/avatars/${u.discord_id}/${u.discord_avatar}.png?size=32`
                      : null;
                    return (
                      <tr key={u._id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2.5">
                            {avatar ? (
                              <img src={avatar} alt="" className="w-7 h-7 rounded-full shrink-0" />
                            ) : (
                              <div className="w-7 h-7 rounded-full bg-indigo-600/30 flex items-center justify-center text-xs font-bold text-indigo-300 shrink-0">
                                {u.discord_username?.[0]?.toUpperCase() || "U"}
                              </div>
                            )}
                            <span className="font-semibold text-white truncate max-w-[140px]">
                              {u.discord_username || "Anonymous"}
                            </span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-slate-300 truncate max-w-[180px]">
                          {u.email || "—"}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                              u.role === "admin"
                                ? "bg-purple-500/15 text-purple-300 border border-purple-500/30"
                                : "bg-slate-500/15 text-slate-300 border border-slate-500/30"
                            }`}
                          >
                            {u.role}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            Active
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-400 text-[11px]">
                          {u.last_login ? new Date(u.last_login).toLocaleDateString() : "Never"}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleToggleUserRole(u)}
                            disabled={updatingUser === u._id}
                            className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-[11px] font-medium border border-white/10 transition-all cursor-pointer disabled:opacity-50"
                          >
                            {updatingUser === u._id
                              ? "Updating…"
                              : u.role === "admin"
                              ? "Demote to User"
                              : "Promote to Admin"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}

        {tab === "jobs" && (
          <motion.div
            key="jobs"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass rounded-2xl overflow-hidden"
          >
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h2 className="font-bold text-sm text-white">Recent Ingested Postings</h2>
              <span className="text-xs text-slate-400">Latest 10 jobs in database</span>
            </div>

            <div className="divide-y divide-white/5">
              {recentJobs.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  No jobs found. Click "Trigger Job Scraper" above to fetch active postings.
                </div>
              ) : (
                recentJobs.map((j) => (
                  <div key={j._id} className="p-4 flex items-center justify-between gap-4 hover:bg-white/[0.02]">
                    <div className="truncate">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-xs truncate">{j.title}</span>
                        {j.is_remote && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                            Remote
                          </span>
                        )}
                      </div>
                      <p className="text-slate-400 text-[11px] mt-0.5">
                        {j.company} · {j.location || "Location unlisted"}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-[10px] text-slate-500 uppercase font-semibold tracking-wider">
                        {j.source || "Feed"}
                      </span>
                      {j.source_url && (
                        <a
                          href={j.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                        >
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}

        {tab === "matches" && (
          <motion.div
            key="matches"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass rounded-2xl overflow-hidden"
          >
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h2 className="font-bold text-sm text-white">Recent Candidate Matches</h2>
              <span className="text-xs text-slate-400">Scored by AI Matcher Engine</span>
            </div>

            <div className="divide-y divide-white/5">
              {recentMatches.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  No candidate matches recorded yet. Matches are computed when the job pipeline evaluates profiles against new jobs.
                </div>
              ) : (
                recentMatches.map((m) => (
                  <div key={m._id} className="p-4 flex items-center justify-between gap-4 hover:bg-white/[0.02]">
                    <div className="truncate">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-xs truncate">
                          {m.job?.title || "Position"}
                        </span>
                        <span className="text-[11px] text-slate-400">at {m.job?.company}</span>
                      </div>
                      <p className="text-slate-400 text-[11px] mt-0.5 truncate max-w-xl">
                        {m.reasoning || "Matched skills & profile preferences"}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <span
                        className={`text-xs font-bold px-2 py-0.5 rounded-md ${
                          m.compatibility_score >= 75
                            ? "text-emerald-400 bg-emerald-500/10 border border-emerald-500/20"
                            : "text-indigo-400 bg-indigo-500/10 border border-indigo-500/20"
                        }`}
                      >
                        {m.compatibility_score}% match
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}

        {tab === "companies" && (
          <motion.div
            key="companies"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-6"
          >
            {/* Grade KPI Summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="glass rounded-xl p-3.5 border border-purple-500/30 bg-purple-500/5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400">Tier-1 Companies</span>
                <p className="text-2xl font-black text-white mt-1">{companyCounts["Tier-1"] || 0}</p>
                <span className="text-[10px] text-slate-400">FAANG, Decacorns & MAANG</span>
              </div>
              <div className="glass rounded-xl p-3.5 border border-cyan-500/30 bg-cyan-500/5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400">Tier-2 Scaleups</span>
                <p className="text-2xl font-black text-white mt-1">{companyCounts["Tier-2"] || 0}</p>
                <span className="text-[10px] text-slate-400">Top Unicorns & Fast Growth</span>
              </div>
              <div className="glass rounded-xl p-3.5 border border-emerald-500/30 bg-emerald-500/5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">Tier-3 Enterprise</span>
                <p className="text-2xl font-black text-white mt-1">{companyCounts["Tier-3"] || 0}</p>
                <span className="text-[10px] text-slate-400">Established Global Tech</span>
              </div>
              <div className="glass rounded-xl p-3.5 border border-white/10 bg-white/5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300">Total in MongoDB</span>
                <p className="text-2xl font-black text-white mt-1">{companyCounts.all || companies.length}</p>
                <span className="text-[10px] text-emerald-400 font-semibold">{companyCounts.active} Active for Scraping</span>
              </div>
            </div>

            {companyActionMsg && (
              <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300 flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{companyActionMsg}</span>
              </div>
            )}

            {/* Filter & Action Toolbar */}
            <div className="glass rounded-2xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
              {/* Grade Pills */}
              <div className="flex flex-wrap items-center gap-1.5">
                {[
                  { id: "all", label: `All (${companyCounts.all || companies.length})` },
                  { id: "Tier-1", label: `Tier-1 (${companyCounts["Tier-1"] || 0})` },
                  { id: "Tier-2", label: `Tier-2 (${companyCounts["Tier-2"] || 0})` },
                  { id: "Tier-3", label: `Tier-3 (${companyCounts["Tier-3"] || 0})` },
                ].map((g) => (
                  <button
                    key={g.id}
                    onClick={() => {
                      setSelectedGrade(g.id);
                      loadCompanies(g.id, companySearch);
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                      selectedGrade === g.id
                        ? "bg-purple-600 text-white shadow-md shadow-purple-600/30"
                        : "bg-white/5 text-slate-400 hover:text-white hover:bg-white/10"
                    }`}
                  >
                    {g.label}
                  </button>
                ))}
              </div>

              {/* Search & Actions */}
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={companySearch}
                    onChange={(e) => {
                      setCompanySearch(e.target.value);
                      loadCompanies(selectedGrade, e.target.value);
                    }}
                    placeholder="Search company, industry, HQ..."
                    className="pl-8 pr-3 py-1.5 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/50 w-52"
                  />
                </div>

                <button
                  onClick={handleSeedCompanies}
                  disabled={seedingCompanies}
                  title="Re-sync verified companies"
                  className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs border border-white/10 transition-all cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${seedingCompanies ? "animate-spin" : ""}`} />
                </button>

                <button
                  onClick={() => setShowAddCompanyModal(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md shadow-purple-600/30 transition-all cursor-pointer shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Company
                </button>
              </div>
            </div>

            {/* Target Companies Table */}
            <div className="glass rounded-2xl overflow-hidden">
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <div>
                  <h2 className="font-bold text-sm text-white">Target Companies Registry</h2>
                  <p className="text-[11px] text-slate-400">
                    Source companies stored in MongoDB collection `companies` with Grade and Career Pages
                  </p>
                </div>
                {loadingCompanies && <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-white/10 text-slate-400 uppercase tracking-wider text-[10px]">
                      <th className="py-3 px-4 font-semibold">Company & Domain</th>
                      <th className="py-3 px-4 font-semibold">Grade</th>
                      <th className="py-3 px-4 font-semibold">ATS Integration</th>
                      <th className="py-3 px-4 font-semibold">Career Page</th>
                      <th className="py-3 px-4 font-semibold">Scrape Status</th>
                      <th className="py-3 px-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {companies.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-12 text-center text-xs text-slate-500">
                          {loadingCompanies ? "Loading companies from MongoDB..." : "No target companies match your filter."}
                        </td>
                      </tr>
                    ) : (
                      companies.map((c) => (
                        <tr key={c._id} className="hover:bg-white/[0.02] transition-colors">
                          {/* Company Name & Details */}
                          <td className="py-3 px-4">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-white text-xs">{c.name}</span>
                                {c.location_hq && (
                                  <span className="text-[10px] text-slate-500 hidden sm:inline">
                                    • {c.location_hq}
                                  </span>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-400 mt-0.5 truncate max-w-xs">
                                {c.industry || "Technology"}
                              </p>
                            </div>
                          </td>

                          {/* Grade Badge */}
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                                c.grade === "Tier-1"
                                  ? "bg-amber-500/15 text-amber-300 border border-amber-500/30 shadow-sm shadow-amber-500/10"
                                  : c.grade === "Tier-2"
                                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                                  : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                              }`}
                            >
                              ★ {c.grade}
                            </span>
                          </td>

                          {/* ATS Integration */}
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-1.5">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                                  c.ats_type === "greenhouse"
                                    ? "bg-emerald-950/40 text-emerald-400 border border-emerald-500/30"
                                    : c.ats_type === "lever"
                                    ? "bg-blue-950/40 text-blue-400 border border-blue-500/30"
                                    : c.ats_type === "ashby"
                                    ? "bg-purple-950/40 text-purple-400 border border-purple-500/30"
                                    : "bg-slate-800 text-slate-400 border border-slate-700"
                                }`}
                              >
                                {c.ats_type}
                              </span>
                              {c.board_token && (
                                <span className="text-[10px] font-mono text-slate-500 truncate max-w-[100px]" title={c.board_token}>
                                  [{c.board_token}]
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Career Page Link */}
                          <td className="py-3 px-4">
                            <a
                              href={c.career_page}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-indigo-300 hover:text-white transition-all text-[11px]"
                            >
                              <span>Career Site</span>
                              <ExternalLink className="w-3 h-3 shrink-0" />
                            </a>
                          </td>

                          {/* Scrape Status Toggle */}
                          <td className="py-3 px-4">
                            <button
                              onClick={() => handleToggleCompany(c)}
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
                                c.is_active
                                  ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25"
                                  : "bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700"
                              }`}
                            >
                              <span
                                className={`w-1.5 h-1.5 rounded-full ${
                                  c.is_active ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
                                }`}
                              />
                              {c.is_active ? "Active" : "Paused"}
                            </button>
                          </td>

                          {/* Actions */}
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => handleDeleteCompany(c._id, c.name)}
                              className="p-1.5 rounded-lg bg-white/5 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 border border-transparent hover:border-rose-500/30 transition-all cursor-pointer"
                              title="Delete from target list"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Add Target Company Modal */}
            <AnimatePresence>
              {showAddCompanyModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="glass rounded-3xl p-6 w-full max-w-md border border-white/15 bg-slate-900/95 shadow-2xl relative"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-4">
                      <div className="flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-purple-400" />
                        <h3 className="font-bold text-white text-sm">Add Target Company</h3>
                      </div>
                      <button
                        onClick={() => setShowAddCompanyModal(false)}
                        className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    <form onSubmit={handleCreateCompany} className="space-y-3.5">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-300 mb-1">Company Name *</label>
                        <input
                          type="text"
                          required
                          value={newCompany.name}
                          onChange={(e) => setNewCompany({ ...newCompany, name: e.target.value })}
                          placeholder="e.g. OpenAI, Stripe, Zepto"
                          className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/60"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] font-semibold text-slate-300 mb-1">Grade / Tier *</label>
                          <select
                            value={newCompany.grade}
                            onChange={(e) => setNewCompany({ ...newCompany, grade: e.target.value })}
                            className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-white/10 text-xs text-white focus:outline-none focus:border-purple-500/60"
                          >
                            <option value="Tier-1">★ Tier-1 (FAANG / Decacorn)</option>
                            <option value="Tier-2">★ Tier-2 (Unicorn / Scaleup)</option>
                            <option value="Tier-3">★ Tier-3 (Enterprise)</option>
                            <option value="Startup">★ Startup</option>
                          </select>
                        </div>

                        <div>
                          <label className="block text-[11px] font-semibold text-slate-300 mb-1">ATS Engine</label>
                          <select
                            value={newCompany.ats_type}
                            onChange={(e) => setNewCompany({ ...newCompany, ats_type: e.target.value })}
                            className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-white/10 text-xs text-white focus:outline-none focus:border-purple-500/60"
                          >
                            <option value="greenhouse">Greenhouse</option>
                            <option value="lever">Lever</option>
                            <option value="ashby">Ashby</option>
                            <option value="custom">Custom / Direct Career Site</option>
                          </select>
                        </div>
                      </div>

                      <div>
                        <label className="block text-[11px] font-semibold text-slate-300 mb-1">Career Page URL *</label>
                        <input
                          type="url"
                          required
                          value={newCompany.career_page}
                          onChange={(e) => setNewCompany({ ...newCompany, career_page: e.target.value })}
                          placeholder="https://company.com/careers"
                          className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/60"
                        />
                      </div>

                      <div>
                        <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                          ATS Board Token <span className="text-[10px] text-slate-500">(Optional - for direct JSON scraper)</span>
                        </label>
                        <input
                          type="text"
                          value={newCompany.board_token}
                          onChange={(e) => setNewCompany({ ...newCompany, board_token: e.target.value })}
                          placeholder="e.g. stripe, openai, datadog"
                          className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/60 font-mono"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] font-semibold text-slate-300 mb-1">Industry</label>
                          <input
                            type="text"
                            value={newCompany.industry}
                            onChange={(e) => setNewCompany({ ...newCompany, industry: e.target.value })}
                            placeholder="e.g. Fintech, AI"
                            className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/60"
                          />
                        </div>

                        <div>
                          <label className="block text-[11px] font-semibold text-slate-300 mb-1">Headquarters</label>
                          <input
                            type="text"
                            value={newCompany.location_hq}
                            onChange={(e) => setNewCompany({ ...newCompany, location_hq: e.target.value })}
                            placeholder="e.g. San Francisco, Bengaluru"
                            className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/60"
                          />
                        </div>
                      </div>

                      <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/10">
                        <button
                          type="button"
                          onClick={() => setShowAddCompanyModal(false)}
                          className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold transition-all cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={savingCompany}
                          className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md shadow-purple-600/30 transition-all cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {savingCompany && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                          Save Company to MongoDB
                        </button>
                      </div>
                    </form>
                  </motion.div>
                </div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
