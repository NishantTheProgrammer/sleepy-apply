"use client";
import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, Building2, Search, Filter, Globe, ArrowUpRight,
  RefreshCw, Sparkles, Loader2, CheckCircle, ShieldCheck,
  ChevronLeft, ChevronRight, X, ExternalLink, MapPin, DollarSign,
  Calendar, Layers, Check
} from "lucide-react";
import Link from "next/link";
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
  });

  const [search, setSearch] = useState("");
  const [selectedCompany, setSelectedCompany] = useState("all");
  const [remoteFilter, setRemoteFilter] = useState<string>("all"); // "all" | "remote" | "onsite"

  const [loading, setLoading] = useState(true);
  const [fetchingLive, setFetchingLive] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

  const [selectedJob, setSelectedJob] = useState<AdminJobRecord | null>(null);

  const loadJobs = useCallback(async (p = page, q = search, comp = selectedCompany, rem = remoteFilter) => {
    setLoading(true);
    try {
      const isRemoteParam = rem === "remote" ? true : rem === "onsite" ? false : undefined;
      const res = await adminApi.allJobs({
        page: p,
        limit,
        search: q || undefined,
        company: comp !== "all" ? comp : undefined,
        is_remote: isRemoteParam,
      });

      setJobs(res.items || []);
      setTotal(res.total || 0);
      setCompanies(res.companies || []);
      if (res.stats) {
        setStats(res.stats);
      }
    } catch (err: unknown) {
      console.error("Failed to load jobs", err);
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, selectedCompany, remoteFilter]);

  useEffect(() => {
    loadJobs(page, search, selectedCompany, remoteFilter);
  }, [page, selectedCompany, remoteFilter, loadJobs]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadJobs(1, search, selectedCompany, remoteFilter);
  };

  const handleFetchLive = async () => {
    setFetchingLive(true);
    try {
      const res = await adminApi.fetchLiveJobs();
      setActionMsg(res.message);
      setTimeout(() => setActionMsg(""), 5000);
      setTimeout(() => loadJobs(page, search, selectedCompany, remoteFilter), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to trigger live fetch";
      alert(msg);
    } finally {
      setFetchingLive(false);
    }
  };

  const handleSeedJobs = async () => {
    if (!confirm("Re-populate MongoDB jobs collection with verified target company listings?")) return;
    setSeeding(true);
    try {
      const res = await adminApi.seedJobs();
      setActionMsg(res.message);
      setTimeout(() => setActionMsg(""), 5000);
      loadJobs(page, search, selectedCompany, remoteFilter);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to seed jobs";
      alert(msg);
    } finally {
      setSeeding(false);
    }
  };

  const totalPages = Math.ceil(total / limit) || 1;

  const cleanDescription = (rawText: string) => {
    if (!rawText) return "No description provided.";
    return rawText
      .replace(/<[^>]+>/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&nbsp;/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-7xl mx-auto">
      {/* ── Top Breadcrumb & Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
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
              All Jobs in MongoDB
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Platform Job Repository</h1>
          <p className="text-slate-400 text-xs mt-1">
            Browse and inspect all raw and enriched job postings stored in MongoDB (`db.jobs`)
          </p>
        </div>

        {/* Global Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => loadJobs(page, search, selectedCompany, remoteFilter)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold border border-white/10 transition-all cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>

          <button
            onClick={handleSeedJobs}
            disabled={seeding}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold border border-white/10 transition-all cursor-pointer disabled:opacity-50"
            title="Seed baseline verified jobs"
          >
            {seeding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Layers className="w-3.5 h-3.5 text-indigo-400" />}
            Seed Baseline Jobs
          </button>

          <button
            onClick={handleFetchLive}
            disabled={fetchingLive}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition-all disabled:opacity-50 cursor-pointer"
          >
            {fetchingLive ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {fetchingLive ? "Scraping Target ATS..." : "Fetch Live ATS Jobs"}
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="mb-6 p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300 flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionMsg}</span>
        </div>
      )}

      {/* ── KPI Stat Cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Total in MongoDB</span>
            <Briefcase className="w-4 h-4 text-purple-400" />
          </div>
          <p className="text-3xl font-black text-white">{stats.total_jobs}</p>
          <span className="text-[10px] text-slate-400">Available across all users</span>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Companies</span>
            <Building2 className="w-4 h-4 text-cyan-400" />
          </div>
          <p className="text-3xl font-black text-white">{stats.companies_count}</p>
          <span className="text-[10px] text-cyan-400 font-semibold">Tier-1, 2 & 3 Target ATS</span>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Remote Positions</span>
            <Globe className="w-4 h-4 text-emerald-400" />
          </div>
          <p className="text-3xl font-black text-white">{stats.remote_jobs}</p>
          <span className="text-[10px] text-emerald-400 font-semibold">Global & Remote-friendly</span>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Active Status</span>
            <CheckCircle className="w-4 h-4 text-indigo-400" />
          </div>
          <p className="text-3xl font-black text-white">{stats.active_jobs}</p>
          <span className="text-[10px] text-indigo-300">Ready for candidate matching</span>
        </motion.div>
      </div>

      {/* ── Search & Filter Toolbar ── */}
      <div className="glass rounded-2xl p-4 mb-6 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        {/* Search Input */}
        <form onSubmit={handleSearchSubmit} className="flex-1 relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by title, company, skills, or location..."
            className="w-full pl-9 pr-20 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/50"
          />
          <button
            type="submit"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 px-2.5 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-[10px] font-bold transition-all cursor-pointer"
          >
            Search
          </button>
        </form>

        {/* Company Dropdown Filter */}
        <div className="flex items-center gap-2">
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
              { id: "onsite", label: "On-site" },
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

          {(search || selectedCompany !== "all" || remoteFilter !== "all") && (
            <button
              onClick={() => {
                setSearch("");
                setSelectedCompany("all");
                setRemoteFilter("all");
                setPage(1);
                loadJobs(1, "", "all", "all");
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
                  <td colSpan={6} className="py-16 text-center text-xs text-slate-500">
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
                              • ${j.salary_range.min.toLocaleString()} - ${j.salary_range.max?.toLocaleString()}
                            </span>
                          )}
                        </div>
                      </div>
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
                        <span className="text-slate-300 text-[11px] truncate max-w-[140px]" title={j.location || "Remote"}>
                          {j.location || "Remote"}
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
                        {(j.required_skills && j.required_skills.length > 0 ? j.required_skills : ["Software Engineering", "Full Stack"]).slice(0, 3).map((s) => (
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
                        {j.application_url && (
                          <a
                            href={j.application_url}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 hover:text-white border border-purple-500/20 transition-all"
                            title="Open Application URL"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* ── Pagination Bar ── */}
        <div className="p-4 border-t border-white/10 flex items-center justify-between text-xs text-slate-400">
          <div>
            Page <span className="font-bold text-white">{page}</span> of{" "}
            <span className="font-bold text-white">{totalPages}</span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 py-1 rounded-lg bg-white/5 font-mono text-white text-xs">
              {page}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Job Details Modal Drawer ── */}
      <AnimatePresence>
        {selectedJob && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass rounded-3xl p-6 w-full max-w-2xl border border-white/15 bg-slate-900/95 shadow-2xl relative max-h-[85vh] flex flex-col"
            >
              {/* Modal Header */}
              <div className="flex items-start justify-between pb-4 border-b border-white/10 shrink-0">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-purple-400">{selectedJob.company}</span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 uppercase">
                      {selectedJob.grade || "Tier-1"}
                    </span>
                    {selectedJob.is_remote && (
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        Remote
                      </span>
                    )}
                  </div>
                  <h3 className="text-lg font-bold text-white">{selectedJob.title}</h3>
                  <p className="text-xs text-slate-400 mt-0.5">{selectedJob.location || "Remote"}</p>
                </div>

                <button
                  onClick={() => setSelectedJob(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="overflow-y-auto py-4 space-y-4 flex-1 pr-1 text-xs text-slate-300 leading-relaxed">
                {selectedJob.required_skills && selectedJob.required_skills.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-white text-[11px] uppercase tracking-wider mb-2">Required Skills</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedJob.required_skills.map((s) => (
                        <span key={s} className="px-2 py-0.5 rounded-md bg-purple-500/15 text-purple-300 border border-purple-500/30 text-xs">
                          {s}
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
                  <h4 className="font-semibold text-white text-[11px] uppercase tracking-wider mb-1">Job Description</h4>
                  <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-300 whitespace-pre-line text-xs">
                    {cleanDescription(selectedJob.description || "")}
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="pt-4 border-t border-white/10 flex items-center justify-between shrink-0">
                <span className="text-[11px] text-slate-500">
                  Source: {selectedJob.source || "company_ats"}
                </span>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSelectedJob(null)}
                    className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold transition-all cursor-pointer"
                  >
                    Close
                  </button>
                  {selectedJob.application_url && (
                    <a
                      href={selectedJob.application_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md shadow-purple-600/30 transition-all"
                    >
                      <span>Apply on Career Site</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
