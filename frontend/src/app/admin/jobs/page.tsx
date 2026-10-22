"use client";
import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, Building2, Search, Filter, Globe, ArrowUpRight,
  RefreshCw, Sparkles, Loader2, CheckCircle, ShieldCheck,
  ChevronLeft, ChevronRight, X, ExternalLink, MapPin, DollarSign,
  Calendar, Layers, Check, Trash2, Zap
} from "lucide-react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { adminApi, AdminJobRecord } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AdminAllJobsPage() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<AdminJobRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);
  const [companies, setCompanies] = useState<string[]>([]);
  const [stats, setStats] = useState({
    total_jobs: 0,
    remote_jobs: 0,
    active_jobs: 0,
    companies_count: 0,
    career_jobs: 0,
    linkedin_jobs: 0,
    naukri_jobs: 0,
  });

  const [search, setSearch] = useState("");
  const [selectedCompany, setSelectedCompany] = useState("all");
  const [selectedSource, setSelectedSource] = useState<string>("all");
  const [remoteFilter, setRemoteFilter] = useState<string>("all"); // "all" | "remote" | "onsite"

  const [loading, setLoading] = useState(true);
  const [fetchingSource, setFetchingSource] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

  const [selectedJob, setSelectedJob] = useState<AdminJobRecord | null>(null);

  const loadJobs = useCallback(async (
    p = page,
    q = search,
    comp = selectedCompany,
    src = selectedSource,
    rem = remoteFilter
  ) => {
    setLoading(true);
    try {
      const isRemoteParam = rem === "remote" ? true : rem === "onsite" ? false : undefined;
      const res = await adminApi.allJobs({
        page: p,
        limit,
        search: q || undefined,
        company: comp !== "all" ? comp : undefined,
        source: src !== "all" ? src : undefined,
        is_remote: isRemoteParam,
      });

      setJobs(res.items || []);
      setTotal(res.total || 0);
      setCompanies(res.companies || []);
      if (res.stats) {
        setStats({
          total_jobs: res.stats.total_jobs || 0,
          remote_jobs: res.stats.remote_jobs || 0,
          active_jobs: res.stats.active_jobs || 0,
          companies_count: res.stats.companies_count || 0,
          career_jobs: res.stats.career_jobs || 0,
          linkedin_jobs: res.stats.linkedin_jobs || 0,
          naukri_jobs: res.stats.naukri_jobs || 0,
        });
      }
    } catch (err: unknown) {
      console.error("Failed to load jobs", err);
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, selectedCompany, selectedSource, remoteFilter]);

  useEffect(() => {
    loadJobs(page, search, selectedCompany, selectedSource, remoteFilter);
  }, [page, selectedCompany, selectedSource, remoteFilter, loadJobs]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadJobs(1, search, selectedCompany, selectedSource, remoteFilter);
  };

  const handleFetchSource = async (src: "all" | "career" | "linkedin" | "naukri") => {
    setFetchingSource(src);
    try {
      const res = await adminApi.fetchLiveJobs(src);
      setActionMsg(res.message);
      setTimeout(() => setActionMsg(""), 6000);
      setTimeout(() => loadJobs(page, search, selectedCompany, selectedSource, remoteFilter), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to trigger live fetch";
      alert(msg);
    } finally {
      setFetchingSource(null);
    }
  };

  const [purging, setPurging] = useState(false);

  const handlePurgeStatic = async () => {
    if (!confirm("Purge all static, seeded, or placeholder listings from MongoDB? Only 100% verified real live postings will remain.")) return;
    setPurging(true);
    try {
      const res = await adminApi.purgeStaticJobs();
      setActionMsg(res.message);
      setTimeout(() => setActionMsg(""), 6000);
      loadJobs(1, search, selectedCompany, selectedSource, remoteFilter);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to purge static jobs";
      alert(msg);
    } finally {
      setPurging(false);
    }
  };

  const handleSyncRealJobs = async () => {
    if (!confirm("Purge any static jobs and sync 100% real live postings from active sources (Career ATS, LinkedIn, Naukri)?")) return;
    setSeeding(true);
    try {
      const res = await adminApi.seedJobs();
      setActionMsg(res.message);
      setTimeout(() => setActionMsg(""), 6000);
      loadJobs(page, search, selectedCompany, selectedSource, remoteFilter);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to sync real jobs";
      alert(msg);
    } finally {
      setSeeding(false);
    }
  };

  const totalPages = Math.ceil(total / limit) || 1;

  const renderSourceBadge = (source?: string) => {
    const s = (source || "career").toLowerCase();
    if (s === "linkedin") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/15 text-sky-400 border border-sky-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
          LinkedIn
        </span>
      );
    }
    if (s === "naukri") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
          Naukri
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
        Career Portal
      </span>
    );
  };

  const getValidJobUrl = (job: AdminJobRecord): string => {
    const url = (job.application_url || job.source_url || "").trim();
    if (!url || url === "https://www.naukri.com/" || url === "https://www.naukri.com") {
      if (job.source?.toLowerCase() === "naukri") {
        const comp = (job.company || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        const titleWords = (job.title || "")
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .split("-")
          .filter((w) => w && !["and", "or", "in", "to", "of", "the", "a", "for", "with"].includes(w))
          .slice(0, 4)
          .join("-");
        if (comp && titleWords) return `https://www.naukri.com/${comp}-${titleWords}-jobs`;
        if (comp) return `https://www.naukri.com/${comp}-jobs`;
        return `https://www.naukri.com/jobs-in-india?k=${encodeURIComponent(job.title || "software engineer")}`;
      }
      return "#";
    }
    return url;
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-7xl mx-auto">
      {/* ── Top Breadcrumb & Header ── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href="/admin"
              className="text-[11px] font-semibold text-slate-400 hover:text-white transition-colors flex items-center gap-1"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
              Admin Center
            </Link>
            <span className="text-slate-600 text-xs">/</span>
            <span className="text-[11px] font-bold text-purple-400 uppercase tracking-wider">
              Multi-Source Job Repository
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Platform Job Repository</h1>
          <p className="text-slate-400 text-xs mt-1">
            Browse and inspect all raw and enriched job postings from Career ATS, LinkedIn, and Naukri stored in MongoDB (`db.jobs`)
          </p>
        </div>

        {/* Global Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => loadJobs(page, search, selectedCompany, selectedSource, remoteFilter)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold border border-white/10 transition-all cursor-pointer"
            title="Refresh current view"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>

          <button
            onClick={handleSyncRealJobs}
            disabled={seeding}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 text-xs font-bold border border-purple-500/30 transition-all cursor-pointer disabled:opacity-50"
            title="Sync 100% real live postings from active sources"
          >
            {seeding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5 text-purple-400" />}
            {seeding ? "Syncing Real..." : "Sync Real Jobs"}
          </button>

          <button
            onClick={handlePurgeStatic}
            disabled={purging}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-semibold border border-red-500/20 transition-all cursor-pointer disabled:opacity-50"
            title="Purge static & placeholder jobs"
          >
            {purging ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5 text-red-400" />}
            {purging ? "Purging..." : "Purge Static"}
          </button>

          {/* Fetch Career ATS Button */}
          <button
            onClick={() => handleFetchSource("career")}
            disabled={Boolean(fetchingSource)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 font-bold text-xs border border-emerald-500/30 shadow-md shadow-emerald-600/10 transition-all disabled:opacity-50 cursor-pointer"
            title="Fetch live postings from Target Company ATS (Greenhouse, Lever, Ashby)"
          >
            {fetchingSource === "career" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Building2 className="w-3.5 h-3.5 text-emerald-400" />}
            {fetchingSource === "career" ? "Fetching ATS..." : "Fetch Career ATS"}
          </button>

          {/* Fetch LinkedIn Button */}
          <button
            onClick={() => handleFetchSource("linkedin")}
            disabled={Boolean(fetchingSource)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 font-bold text-xs border border-sky-500/30 shadow-md shadow-sky-600/10 transition-all disabled:opacity-50 cursor-pointer"
            title="Fetch live tech jobs from LinkedIn India"
          >
            {fetchingSource === "linkedin" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Briefcase className="w-3.5 h-3.5 text-sky-400" />}
            {fetchingSource === "linkedin" ? "Fetching LinkedIn..." : "Fetch LinkedIn"}
          </button>

          {/* Fetch Naukri Button */}
          <button
            onClick={() => handleFetchSource("naukri")}
            disabled={Boolean(fetchingSource)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 font-bold text-xs border border-amber-500/30 shadow-md shadow-amber-600/10 transition-all disabled:opacity-50 cursor-pointer"
            title="Fetch live tech postings from Naukri India"
          >
            {fetchingSource === "naukri" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Globe className="w-3.5 h-3.5 text-amber-400" />}
            {fetchingSource === "naukri" ? "Fetching Naukri..." : "Fetch Naukri"}
          </button>

          {/* Fetch All Sources Button */}
          <button
            onClick={() => handleFetchSource("all")}
            disabled={Boolean(fetchingSource)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition-all disabled:opacity-50 cursor-pointer"
            title="Fetch all sources concurrently"
          >
            {fetchingSource === "all" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {fetchingSource === "all" ? "Fetching All..." : "Fetch All Sources"}
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="mb-6 p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300 flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionMsg}</span>
        </div>
      )}

      {/* ── KPI Stat Cards (With Source Breakdown) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {/* Total */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-3.5">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Total in MongoDB</span>
            <Briefcase className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <p className="text-2xl font-black text-white">{stats.total_jobs}</p>
          <span className="text-[10px] text-slate-400">All sources</span>
        </motion.div>

        {/* Career ATS */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 }} className="glass rounded-2xl p-3.5 border-emerald-500/20">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">Career ATS</span>
            <Building2 className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <p className="text-2xl font-black text-emerald-400">{stats.career_jobs || 0}</p>
          <span className="text-[10px] text-emerald-500/80 font-medium">Portals & ATS</span>
        </motion.div>

        {/* LinkedIn */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} className="glass rounded-2xl p-3.5 border-sky-500/20">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-sky-400">LinkedIn</span>
            <Briefcase className="w-3.5 h-3.5 text-sky-400" />
          </div>
          <p className="text-2xl font-black text-sky-400">{stats.linkedin_jobs || 0}</p>
          <span className="text-[10px] text-sky-500/80 font-medium">LinkedIn India</span>
        </motion.div>

        {/* Naukri */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="glass rounded-2xl p-3.5 border-amber-500/20">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400">Naukri</span>
            <Globe className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <p className="text-2xl font-black text-amber-400">{stats.naukri_jobs || 0}</p>
          <span className="text-[10px] text-amber-500/80 font-medium">Naukri India</span>
        </motion.div>

        {/* Remote Positions */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }} className="glass rounded-2xl p-3.5">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Remote</span>
            <Globe className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <p className="text-2xl font-black text-white">{stats.remote_jobs}</p>
          <span className="text-[10px] text-indigo-400 font-semibold">Remote-friendly</span>
        </motion.div>

        {/* Companies */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-2xl p-3.5">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Companies</span>
            <Building2 className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <p className="text-2xl font-black text-white">{stats.companies_count}</p>
          <span className="text-[10px] text-cyan-400 font-semibold">Distinct Orgs</span>
        </motion.div>
      </div>

      {/* ── Search & Multi-Source Filter Toolbar ── */}
      <div className="glass rounded-2xl p-4 mb-6 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
        {/* Search Input */}
        <form onSubmit={handleSearchSubmit} className="flex-1 relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, company, skills, or location..."
            className="w-full pl-9 pr-20 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/50"
          />
          <button
            type="submit"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 px-2.5 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-bold transition-all cursor-pointer"
          >
            Search
          </button>
        </form>

        {/* Source Filter Tabs */}
        <div className="flex items-center rounded-xl bg-white/5 border border-white/10 p-0.5 shrink-0 flex-wrap">
          {[
            { id: "all", label: `All (${stats.total_jobs})` },
            { id: "career", label: `Career ATS (${stats.career_jobs || 0})` },
            { id: "linkedin", label: `LinkedIn (${stats.linkedin_jobs || 0})` },
            { id: "naukri", label: `Naukri (${stats.naukri_jobs || 0})` },
          ].map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setSelectedSource(s.id);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                selectedSource === s.id
                  ? s.id === "linkedin"
                    ? "bg-sky-600 text-white shadow-sm"
                    : s.id === "naukri"
                    ? "bg-amber-600 text-white shadow-sm"
                    : s.id === "career"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-purple-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Company & Remote Filters */}
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={selectedCompany}
            onChange={(e) => {
              setSelectedCompany(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 rounded-xl bg-slate-900 border border-white/10 text-xs text-white focus:outline-none focus:border-purple-500/50"
          >
            <option value="all">All Companies ({companies.length})</option>
            {companies.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          {/* Remote Toggle */}
          <div className="flex items-center rounded-xl bg-white/5 border border-white/10 p-0.5">
            {[
              { id: "all", label: "All" },
              { id: "remote", label: "Remote" },
              { id: "onsite", label: "Onsite" },
            ].map((r) => (
              <button
                key={r.id}
                onClick={() => {
                  setRemoteFilter(r.id);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  remoteFilter === r.id
                    ? "bg-purple-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {(search || selectedCompany !== "all" || selectedSource !== "all" || remoteFilter !== "all") && (
            <button
              onClick={() => {
                setSearch("");
                setSelectedCompany("all");
                setSelectedSource("all");
                setRemoteFilter("all");
                setPage(1);
                loadJobs(1, "", "all", "all", "all");
              }}
              className="text-[11px] text-slate-400 hover:text-rose-400 px-2 py-1 underline transition-colors cursor-pointer"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* ── Jobs Table & Cards ── */}
      <div className="glass rounded-2xl overflow-hidden mb-6">
        <div className="p-4 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="font-bold text-sm text-white">MongoDB Ingested Jobs</h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-bold">
              Showing {jobs.length} of {total} jobs
            </span>
          </div>
          {loading && <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/10 text-slate-400 uppercase tracking-wider text-[10px]">
                <th className="py-3 px-4 font-semibold">Job Title & Details</th>
                <th className="py-3 px-4 font-semibold">Source</th>
                <th className="py-3 px-4 font-semibold">Company & Grade</th>
                <th className="py-3 px-4 font-semibold">Location</th>
                <th className="py-3 px-4 font-semibold">Required Skills</th>
                <th className="py-3 px-4 font-semibold">Discovered</th>
                <th className="py-3 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-xs text-slate-500">
                    {loading ? "Loading jobs from MongoDB..." : "No job postings matched your filters."}
                  </td>
                </tr>
              ) : (
                jobs.map((j) => (
                  <tr key={j._id} className="hover:bg-white/[0.02] transition-colors">
                    {/* Job Title */}
                    <td className="py-3 px-4 max-w-sm">
                      <div>
                        <span className="font-bold text-white text-xs hover:text-purple-300 transition-colors">
                          {j.title}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] text-slate-500 uppercase tracking-wider font-mono">
                            ID: {j._id.slice(-6)}
                          </span>
                          {j.employment_type && (
                            <span className="text-[10px] text-slate-400 capitalize">
                              • {j.employment_type}
                            </span>
                          )}
                          {j.salary_range?.min && (
                            <span className="text-[10px] text-emerald-400 font-semibold">
                              • {j.salary_range.currency === "INR" ? "₹" : "$"}{j.salary_range.min.toLocaleString()} - {j.salary_range.currency === "INR" ? "₹" : "$"}{j.salary_range.max?.toLocaleString()}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Source Badge */}
                    <td className="py-3 px-4">
                      {renderSourceBadge(j.source)}
                    </td>

                    {/* Company & Grade */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">{j.company}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${
                            j.grade === "Tier-1"
                              ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                              : j.grade === "Tier-2"
                              ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                              : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          }`}
                        >
                          {j.grade || "Tier-1"}
                        </span>
                      </div>
                    </td>

                    {/* Location & Remote */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        <MapPin className="w-3 h-3 text-slate-500 shrink-0" />
                        <span className="text-slate-300 text-[11px] truncate max-w-[140px]" title={j.location || "India"}>
                          {j.location || "India"}
                        </span>
                      </div>
                      {j.is_remote && (
                        <span className="inline-block mt-0.5 text-[10px] font-semibold text-emerald-400">
                          100% Remote
                        </span>
                      )}
                    </td>

                    {/* Skills */}
                    <td className="py-3 px-4 max-w-xs">
                      <div className="flex flex-wrap gap-1">
                        {(j.required_skills && j.required_skills.length > 0 ? j.required_skills : ["Software Engineering"]).slice(0, 3).map((s) => (
                          <span
                            key={s}
                            className="text-[10px] px-1.5 py-0.2 rounded bg-white/5 border border-white/10 text-slate-300"
                          >
                            {s}
                          </span>
                        ))}
                        {(j.required_skills?.length || 0) > 3 && (
                          <span className="text-[10px] text-slate-500 font-mono">
                            +{(j.required_skills?.length || 0) - 3}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Discovered At */}
                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      {j.discovered_at ? new Date(j.discovered_at).toLocaleDateString() : "Recent"}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => setSelectedJob(j)}
                          className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-[11px] font-medium border border-white/10 transition-all cursor-pointer"
                        >
                          View JD
                        </button>
                        <a
                          href={getValidJobUrl(j)}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white border border-white/10 transition-all"
                          title="Open external apply page"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-white/10 flex items-center justify-between text-xs text-slate-400">
            <div>
              Page <span className="font-bold text-white">{page}</span> of{" "}
              <span className="font-bold text-white">{totalPages}</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1 cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" /> Previous
              </button>
              <button
                onClick={() => setPage((prev) => Math.min(prev + 1, totalPages))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1 cursor-pointer"
              >
                Next <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Slide-over / Modal for Full Job Details ── */}
      <AnimatePresence>
        {selectedJob && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="glass rounded-3xl max-w-2xl w-full max-h-[85vh] flex flex-col p-6 shadow-2xl border border-white/15 overflow-hidden"
            >
              {/* Modal Header */}
              <div className="flex items-start justify-between pb-4 border-b border-white/10 shrink-0">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    {renderSourceBadge(selectedJob.source)}
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-purple-500/15 text-purple-300 border border-purple-500/30">
                      {selectedJob.grade || "Tier-1"}
                    </span>
                    {selectedJob.is_remote && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        100% Remote
                      </span>
                    )}
                  </div>
                  <h3 className="text-xl font-black text-white">{selectedJob.title}</h3>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                    <span className="font-semibold text-slate-200">{selectedJob.company}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-slate-500" />
                      {selectedJob.location || "India"}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedJob(null)}
                  className="p-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto py-4 space-y-4 text-xs pr-2">
                {selectedJob.required_skills && selectedJob.required_skills.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-white text-[11px] uppercase tracking-wider mb-2">Required Skills</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedJob.required_skills.map((skill) => (
                        <span
                          key={skill}
                          className="px-2.5 py-1 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-300 font-medium text-xs"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {selectedJob.requirements && selectedJob.requirements.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-white text-[11px] uppercase tracking-wider mb-2">Requirements</h4>
                    <ul className="list-disc pl-4 space-y-1 text-slate-400">
                      {selectedJob.requirements.map((req, i) => (
                        <li key={i}>{req}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {selectedJob.responsibilities && selectedJob.responsibilities.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-white text-[11px] uppercase tracking-wider mb-2">Responsibilities</h4>
                    <ul className="list-disc pl-4 space-y-1 text-slate-400">
                      {selectedJob.responsibilities.map((resp, i) => (
                        <li key={i}>{resp}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div>
                  <h4 className="font-semibold text-white text-[11px] uppercase tracking-wider mb-2">Job Description</h4>
                  <div className="p-4 rounded-xl bg-white/[0.03] border border-white/5 text-slate-300 text-xs leading-relaxed max-w-none prose prose-invert">
                    <ReactMarkdown>{selectedJob.description || "No description provided."}</ReactMarkdown>
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="pt-4 border-t border-white/10 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-slate-500">Source:</span>
                  {renderSourceBadge(selectedJob.source)}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSelectedJob(null)}
                    className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold transition-all cursor-pointer"
                  >
                    Close
                  </button>
                  <a
                    href={getValidJobUrl(selectedJob)}
                    target="_blank"
                    rel="noreferrer"
                    className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-white font-bold text-xs shadow-md transition-all ${
                        selectedJob.source === "linkedin"
                          ? "bg-sky-600 hover:bg-sky-500 shadow-sky-600/30"
                          : selectedJob.source === "naukri"
                          ? "bg-amber-600 hover:bg-amber-500 shadow-amber-600/30"
                          : "bg-purple-600 hover:bg-purple-500 shadow-purple-600/30"
                      }`}
                    >
                      <span>
                        {selectedJob.source === "linkedin"
                          ? "Apply on LinkedIn"
                          : selectedJob.source === "naukri"
                          ? "Apply on Naukri"
                          : "Apply on Career Portal"}
                      </span>
                      <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
