"use client";
import { useEffect, useState, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, MapPin, Building2, Zap, CheckCircle, Loader2, Sparkles,
  ExternalLink, Search, Check, AlertTriangle, FileText, ChevronRight,
  SlidersHorizontal, ChevronLeft, Award, Globe, ShieldCheck, X,
  Eye, Download, RefreshCw, Copy, FileCode
} from "lucide-react";
import { jobsApi } from "@/lib/api";

export interface TailoredResumeContent {
  job_id?: string;
  job_title?: string;
  company?: string;
  tailored_summary?: string;
  matching_skills?: string[];
  required_skills?: string[];
  personal?: {
    name?: string;
    full_name?: string;
    fullName?: string;
    email?: string;
    phone?: string;
    location?: unknown;
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
  summary?: string;
  skills?: Record<string, string[]> | string[];
  experience?: Array<{
    title?: string;
    company?: string;
    location?: unknown;
    start_date?: string;
    end_date?: string;
    current?: boolean;
    description?: string;
    highlights?: string[];
  }>;
  education?: Array<{
    degree?: string;
    field?: string;
    institution?: string;
    year?: string;
    grade?: string;
  }>;
  projects?: Array<{
    title?: string;
    description?: string;
    tech_stack?: string[];
    link?: string;
  }>;
  achievements?: string[];
  template?: string;
  generated_at?: string;
}

interface JobItem {
  _id: string;
  job_id: string;
  user_id: string;
  compatibility_score: number;
  match_reasoning?: string;
  matching_skills: string[];
  missing_skills: string[];
  score_breakdown?: {
    skills?: number;
    location?: number;
    title?: number;
    experience?: number;
  };
  tailored_resume?: TailoredResumeContent;
  resume_generated_at?: string;
  resume_docx_path?: string;
  job: {
    _id: string;
    title: string;
    company: string;
    location: string | Record<string, unknown>;
    is_remote: boolean;
    application_url: string;
    source?: string;
    source_url?: string;
    description?: string;
    requirements?: string[];
    responsibilities?: string[];
    required_skills?: string[];
    salary_range?: { min?: number; max?: number; currency?: string };
    grade?: string;
    employment_type?: string;
    discovered_at?: string;
  };
  application?: {
    _id?: string;
    status: string;
    created_at?: string;
    updated_at?: string;
  };
}

function formatLocation(loc: unknown): string {
  if (!loc) return "";
  if (typeof loc === "string") return loc;
  if (typeof loc === "object" && loc !== null) {
    const l = loc as Record<string, unknown>;
    const city = typeof l.city === "string" ? l.city.trim() : "";
    const country = typeof l.country === "string" ? l.country.trim() : "";
    const address = typeof l.address === "string" ? l.address.trim() : "";
    if (city && country) return `${city}, ${country}`;
    if (city) return city;
    if (country) return country;
    if (address) return address;
  }
  return "";
}

const STATUS_STYLE: Record<string, string> = {
  VERIFIED_SUCCESS: "text-emerald-300 bg-emerald-400/10 border-emerald-400/20",
  APPLIED:          "text-blue-300 bg-blue-400/10 border-blue-400/20",
  APPLYING:         "text-yellow-300 bg-yellow-400/10 border-yellow-400/20",
  FAILED:           "text-red-300 bg-red-400/10 border-red-400/20",
  REQUIRES_USER_ACTION: "text-orange-300 bg-orange-400/10 border-orange-400/20",
};

function JobsPageContent() {
  const searchParams = useSearchParams();
  const preselectedId = searchParams.get("selected");

  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState("");

  // Filters & Selected Job
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTab, setFilterTab] = useState<"all" | "high" | "remote" | "bengaluru">("all");
  const [descExpanded, setDescExpanded] = useState(false);

  // Tailored Resume State & Modal
  const [generatingResumeId, setGeneratingResumeId] = useState<string | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewItem, setPreviewItem] = useState<JobItem | null>(null);
  const [previewTab, setPreviewTab] = useState<"doc" | "json">("doc");
  const [copiedJson, setCopiedJson] = useState(false);

  const load = async (p = 1) => {
    setLoading(true);
    try {
      const res = await jobsApi.list({ page: p, limit: 30 });
      const items = (res.items || []) as JobItem[];
      setJobs(items);
      setTotal(res.total || items.length);
      setPage(p);

      // Default select the requested job from query or the first job
      if (items.length > 0) {
        if (preselectedId) {
          const found = items.find((j) => j.job._id === preselectedId || j._id === preselectedId);
          setSelectedJobId(found ? found.job._id : items[0].job._id);
        } else if (!selectedJobId) {
          setSelectedJobId(items[0].job._id);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDiscoverJobs = async () => {
    setDiscovering(true);
    setDiscoverMsg("");
    try {
      const res = await jobsApi.fetchNow();
      setDiscoverMsg(res.message || "Discovery started! Matching jobs to your profile…");
      setTimeout(() => load(1), 3000);
      setTimeout(() => load(1), 7000);
      setTimeout(() => {
        load(1);
        setDiscovering(false);
      }, 10000);
    } catch (err: unknown) {
      setDiscoverMsg(err instanceof Error ? err.message : "Failed to trigger discovery");
      setDiscovering(false);
    }
  };

  const handleApply = async (jobId: string) => {
    setApplying(jobId);
    try {
      await jobsApi.apply(jobId);
      await load(page);
    } catch (e) {
      console.error(e);
    } finally {
      setApplying(null);
    }
  };

  const handleGenerateResume = async (jobId: string, openPreview = false) => {
    setGeneratingResumeId(jobId);
    try {
      const res = await jobsApi.generateResume(jobId);
      if (res.ok && res.tailored_resume) {
        setJobs((prev) =>
          prev.map((item) => {
            if (item.job._id === jobId || item._id === jobId || item.job_id === jobId) {
              const updatedItem: JobItem = {
                ...item,
                tailored_resume: res.tailored_resume as TailoredResumeContent,
                resume_generated_at: res.generated_at,
              };
              if (openPreview) {
                setPreviewItem(updatedItem);
                setPreviewModalOpen(true);
              }
              return updatedItem;
            }
            return item;
          })
        );
      }
    } catch (err) {
      console.error("Failed to generate tailored resume:", err);
    } finally {
      setGeneratingResumeId(null);
    }
  };

  const handleOpenPreview = async (item: JobItem) => {
    if (!item.tailored_resume) {
      await handleGenerateResume(item.job._id, true);
    } else {
      setPreviewItem(item);
      setPreviewModalOpen(true);
      setPreviewTab("doc");
    }
  };

  const handleCopyJson = (data: unknown) => {
    try {
      navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 2000);
    } catch (e) {
      console.error(e);
    }
  };

  // Filtered jobs list
  const filteredJobs = useMemo(() => {
    return jobs.filter((item) => {
      const q = searchQuery.toLowerCase().trim();
      const jobLoc = formatLocation(item.job.location).toLowerCase();
      const matchesSearch =
        !q ||
        item.job.title.toLowerCase().includes(q) ||
        item.job.company.toLowerCase().includes(q) ||
        jobLoc.includes(q);

      if (!matchesSearch) return false;

      if (filterTab === "high") {
        return item.compatibility_score >= 75;
      }
      if (filterTab === "remote") {
        return item.job.is_remote || jobLoc.includes("remote");
      }
      if (filterTab === "bengaluru") {
        return jobLoc.includes("bengaluru") || jobLoc.includes("bangalore");
      }
      return true;
    });
  }, [jobs, searchQuery, filterTab]);

  // Currently selected job object
  const selectedItem = useMemo(() => {
    if (!selectedJobId) return filteredJobs[0] || jobs[0] || null;
    return (
      jobs.find((j) => j.job._id === selectedJobId || j._id === selectedJobId) ||
      filteredJobs[0] ||
      null
    );
  }, [selectedJobId, jobs, filteredJobs]);

  return (
    <div className="p-4 sm:p-6 md:p-8 max-w-full min-w-0">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              🇮🇳 India Tech Openings Only
            </span>
            <span className="text-xs text-slate-400">
              {total} Verified Indian Positions
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Matched Jobs (India)</h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-0.5">
            Active tech openings across Bengaluru, Hyderabad, Pune, Gurugram, Mumbai, and Remote (India).
          </p>
        </div>

        <button
          onClick={handleDiscoverJobs}
          disabled={discovering}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 cursor-pointer self-start sm:self-auto shrink-0"
        >
          {discovering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
          {discovering ? "Discovering & Scoring…" : "Discover Jobs Now"}
        </button>
      </div>

      {discoverMsg && (
        <div className="mb-6 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0 text-indigo-400" />
          <span>{discoverMsg}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="glass rounded-2xl p-3 mb-6 flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by job title, company name, or keywords…"
            className="w-full pl-10 pr-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
          <button
            onClick={() => setFilterTab("all")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              filterTab === "all"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/20"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            All India ({jobs.length})
          </button>
          <button
            onClick={() => setFilterTab("bengaluru")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              filterTab === "bengaluru"
                ? "bg-purple-600 text-white shadow-md shadow-purple-600/20"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            Bengaluru / Bangalore
          </button>
          <button
            onClick={() => setFilterTab("remote")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              filterTab === "remote"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/20"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            Remote (India)
          </button>
          <button
            onClick={() => setFilterTab("high")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              filterTab === "high"
                ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/20"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            High Match (≥75%)
          </button>
        </div>
      </div>

      {/* Main Split-View Layout */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* ── LEFT COLUMN: MASTER JOB LIST (Cols 1-7) ── */}
        <div className="xl:col-span-7 space-y-3">
          {loading ? (
            <div className="glass rounded-2xl p-16 flex flex-col justify-center items-center gap-3 text-slate-400 text-sm">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
              <span>Scoring jobs against candidate profile…</span>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="glass rounded-2xl p-10 text-center">
              <Briefcase className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-white mb-1">No jobs match your filter</h3>
              <p className="text-slate-400 text-xs max-w-sm mx-auto mb-5 leading-relaxed">
                Try resetting your search query or running the live AI discovery pipeline to fetch fresh positions.
              </p>
              <button
                onClick={() => {
                  setSearchQuery("");
                  setFilterTab("all");
                }}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-slate-300 font-semibold cursor-pointer"
              >
                Reset Filters
              </button>
            </div>
          ) : (
            filteredJobs.map((item, i) => {
              const score = item.compatibility_score;
              const isSelected = selectedItem?.job._id === item.job._id;
              const appStatus = item.application?.status;
              const isHigh = score >= 75;
              const isMed = score >= 50 && score < 75;

              return (
                <motion.div
                  key={item._id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.02 }}
                  onClick={() => setSelectedJobId(item.job._id)}
                  className={`p-4 rounded-2xl cursor-pointer transition-all relative overflow-hidden ${
                    isSelected
                      ? "glass border-indigo-500 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30 bg-white/[0.08]"
                      : "glass glass-hover hover:border-white/20"
                  }`}
                >
                  {/* Selected Indicator Accent */}
                  {isSelected && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-indigo-500 to-purple-500" />
                  )}

                  <div className="flex items-start gap-3.5">
                    {/* Score Badge */}
                    <div
                      className={`w-12 h-12 shrink-0 rounded-xl flex flex-col items-center justify-center font-black ${
                        isHigh
                          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                          : isMed
                          ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                          : "bg-red-500/15 text-red-400 border border-red-500/30"
                      }`}
                    >
                      <span className="text-base leading-none">{score}</span>
                      <span className="text-[8px] uppercase tracking-wider font-semibold opacity-70">pts</span>
                    </div>

                    {/* Job Summary */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className={`font-bold text-sm truncate ${isSelected ? "text-indigo-300" : "text-white"}`}>
                            {item.job.title}
                          </h3>
                          <div className="flex items-center gap-2 mt-1 text-xs text-slate-400 flex-wrap">
                            <span className="font-semibold text-slate-300 flex items-center gap-1">
                              <Building2 className="w-3 h-3 text-slate-500" /> {item.job.company}
                            </span>
                            <span>•</span>
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3 h-3 text-slate-500" /> {formatLocation(item.job.location) || "Bengaluru, India"}
                            </span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-medium">
                              🇮🇳 India
                            </span>
                          </div>
                        </div>

                        {/* Status Tag or Selected Pill */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          {appStatus && (
                            <span className={`text-[10px] px-2 py-0.5 rounded border font-semibold ${STATUS_STYLE[appStatus] || "text-slate-400 bg-white/5 border-white/10"}`}>
                              {appStatus.replace(/_/g, " ")}
                            </span>
                          )}
                          {isSelected && (
                            <span className="hidden sm:inline-flex text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">
                              Viewing
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Matching and Missing Skills */}
                      <div className="mt-2.5 flex flex-wrap gap-1">
                        {(item.matching_skills || []).slice(0, 4).map((s) => (
                          <span
                            key={s}
                            className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 flex items-center gap-0.5"
                          >
                            <Check className="w-2.5 h-2.5" /> {s}
                          </span>
                        ))}
                        {(item.missing_skills || []).slice(0, 2).map((s) => (
                          <span
                            key={s}
                            className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20"
                          >
                            {s}
                          </span>
                        ))}
                      </div>

                      {/* Tailored Resume Status & Quick Action */}
                      <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-xs">
                        {item.tailored_resume ? (
                          <div className="flex items-center gap-1.5 text-purple-300">
                            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                            <span className="text-[10px] font-semibold">Tailored Resume Ready</span>
                          </div>
                        ) : (
                          <div className="text-[10px] text-slate-500">
                            No tailored resume yet
                          </div>
                        )}

                        <div className="flex items-center gap-1.5">
                          {item.tailored_resume ? (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenPreview(item);
                              }}
                              className="px-2 py-1 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/20 text-[10px] font-semibold flex items-center gap-1 transition-all cursor-pointer"
                              title="Preview tailored resume and JSON"
                            >
                              <Eye className="w-3 h-3" /> Preview
                            </button>
                          ) : (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleGenerateResume(item.job._id, true);
                              }}
                              disabled={generatingResumeId === item.job._id}
                              className="px-2 py-1 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/20 text-[10px] font-semibold flex items-center gap-1 transition-all cursor-pointer disabled:opacity-50"
                              title="Generate tailored resume"
                            >
                              {generatingResumeId === item.job._id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Sparkles className="w-3 h-3" />
                              )}
                              Tailor Resume
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })
          )}
        </div>

        {/* ── RIGHT COLUMN: JOB INSPECTOR SIDE PANEL (Cols 8-12, Sticky) ── */}
        <div className="xl:col-span-5 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto custom-scrollbar space-y-4">
          {selectedItem ? (
            <AnimatePresence mode="wait">
              <motion.div
                key={selectedItem.job._id}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.15 }}
                className="space-y-4"
              >
                {/* 1. Header & Primary CTA Card */}
                <div className="glass rounded-2xl p-5 border border-indigo-500/20 relative overflow-hidden">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                        {selectedItem.job.company}
                      </span>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                        🇮🇳 India
                      </span>
                      {selectedItem.job.is_remote && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">
                          Remote
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono">
                      ATS Verified
                    </span>
                  </div>

                  <h2 className="text-xl font-black text-white mb-2 leading-snug">
                    {selectedItem.job.title}
                  </h2>

                  <div className="flex items-center gap-3 text-xs text-slate-400 mb-4 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Building2 className="w-3.5 h-3.5 text-slate-500" /> {selectedItem.job.company}
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-500" /> {formatLocation(selectedItem.job.location) || "Remote"}
                    </span>
                    {selectedItem.job.employment_type && (
                      <>
                        <span>•</span>
                        <span className="capitalize">{selectedItem.job.employment_type}</span>
                      </>
                    )}
                  </div>

                  {/* Primary Action Row */}
                  <div className="flex items-center gap-2 pt-2 border-t border-white/10">
                    <button
                      onClick={() => handleApply(selectedItem.job._id)}
                      disabled={applying === selectedItem.job._id || ["APPLIED", "VERIFIED_SUCCESS"].includes(selectedItem.application?.status || "")}
                      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all cursor-pointer disabled:opacity-60"
                    >
                      {applying === selectedItem.job._id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : selectedItem.application?.status === "APPLIED" || selectedItem.application?.status === "VERIFIED_SUCCESS" ? (
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-300" />
                      ) : (
                        <Zap className="w-3.5 h-3.5" />
                      )}
                      {applying === selectedItem.job._id
                        ? "Executing LangGraph Apply Pipeline…"
                        : selectedItem.application?.status === "APPLIED"
                        ? "Applied with AI"
                        : "One-Click Auto-Apply with AI"}
                    </button>

                    {selectedItem.tailored_resume ? (
                      <button
                        onClick={() => handleOpenPreview(selectedItem)}
                        className="px-3 py-2.5 rounded-xl border border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer shrink-0"
                        title="Preview tailored resume & JSON"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Preview</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleGenerateResume(selectedItem.job._id, true)}
                        disabled={generatingResumeId === selectedItem.job._id}
                        className="px-3 py-2.5 rounded-xl border border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50 shrink-0"
                        title="Generate tailored resume"
                      >
                        {generatingResumeId === selectedItem.job._id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        <span className="hidden sm:inline">Tailor Resume</span>
                      </button>
                    )}

                    <a
                      href={selectedItem.job.application_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5 transition-all shrink-0"
                      title="Open official career page"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                </div>

                {/* 2. AI Match Compatibility Breakdown */}
                <div className="glass rounded-2xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-indigo-400" />
                      <h3 className="text-sm font-bold text-white">AI Compatibility Breakdown</h3>
                    </div>
                    <span
                      className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        selectedItem.compatibility_score >= 75
                          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                          : "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                      }`}
                    >
                      {selectedItem.compatibility_score}% Compatibility
                    </span>
                  </div>

                  {/* Match reasoning text */}
                  {selectedItem.match_reasoning ? (
                    <div className="p-3 rounded-xl bg-indigo-500/5 border border-indigo-500/15 text-xs text-slate-300 leading-relaxed mb-4">
                      <p className="font-semibold text-indigo-300 text-[11px] mb-1">AI Match Rationale:</p>
                      {selectedItem.match_reasoning}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                      Your technical experience and stack match {selectedItem.compatibility_score}% of the required competencies for this opening at {selectedItem.job.company}.
                    </p>
                  )}

                  {/* Matching Skills */}
                  <div className="mb-4">
                    <p className="text-[10px] uppercase tracking-wider font-semibold text-emerald-400 mb-2 flex items-center gap-1.5">
                      <Check className="w-3 h-3" /> Matching Candidate Skills ({selectedItem.matching_skills.length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedItem.matching_skills.map((skill) => (
                        <span
                          key={skill}
                          className="px-2 py-1 rounded-lg text-xs font-medium bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Missing Skills */}
                  {selectedItem.missing_skills.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider font-semibold text-amber-400 mb-2 flex items-center gap-1.5">
                        <AlertTriangle className="w-3 h-3" /> Missing / Growth Requirements ({selectedItem.missing_skills.length})
                      </p>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {selectedItem.missing_skills.map((skill) => (
                          <span
                            key={skill}
                            className="px-2 py-1 rounded-lg text-xs font-medium bg-amber-500/10 border border-amber-500/20 text-amber-300"
                          >
                            {skill}
                          </span>
                        ))}
                      </div>
                      <p className="text-[11px] text-slate-500">
                        The AI Resume Tailor will emphasize adjacent experience to bridge these requirements during auto-submission.
                      </p>
                    </div>
                  )}
                </div>

                {/* 3. Tailored Resume & Materials Preview */}
                <div className="glass rounded-2xl p-5 border border-purple-500/20 relative overflow-hidden">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-purple-400" />
                      <h3 className="text-sm font-bold text-white">AI Tailored Resume Variant</h3>
                    </div>
                    {selectedItem.tailored_resume ? (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center gap-1">
                        <Check className="w-2.5 h-2.5" /> Stored in Match Listing
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/10">
                        Not Generated Yet
                      </span>
                    )}
                  </div>

                  {selectedItem.tailored_resume ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>
                          Template:{" "}
                          <strong className="text-slate-200">
                            {selectedItem.tailored_resume.template === "classic_ats" ? "Classic ATS" : "Default Template (Google Doc)"}
                          </strong>
                        </span>
                        {selectedItem.resume_generated_at && (
                          <span className="text-[11px] text-slate-500">
                            {new Date(selectedItem.resume_generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>

                      <div className="p-3 rounded-xl bg-purple-500/5 border border-purple-500/15 text-xs text-slate-300 leading-relaxed">
                        <p className="font-semibold text-purple-300 text-[11px] mb-1 flex items-center gap-1.5">
                          <Sparkles className="w-3 h-3 text-purple-400" /> Tailored Profile Pitch:
                        </p>
                        {selectedItem.tailored_resume.tailored_summary || selectedItem.tailored_resume.summary}
                      </div>

                      {/* Matching Skills Prioritized */}
                      {selectedItem.tailored_resume.matching_skills && selectedItem.tailored_resume.matching_skills.length > 0 && (
                        <div className="text-xs">
                          <p className="text-[10px] uppercase tracking-wider font-semibold text-purple-300 mb-1.5">
                            Prioritized JD Skills ({selectedItem.tailored_resume.matching_skills.length})
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {selectedItem.tailored_resume.matching_skills.map((s) => (
                              <span
                                key={s}
                                className="px-1.5 py-0.5 rounded text-[10px] bg-purple-500/10 text-purple-300 border border-purple-500/20"
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Action Buttons */}
                      <div className="pt-2 border-t border-white/5 flex items-center gap-2">
                        <button
                          onClick={() => handleOpenPreview(selectedItem)}
                          className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md shadow-purple-600/20 transition-all cursor-pointer"
                        >
                          <Eye className="w-3.5 h-3.5" /> Preview Resume & JSON
                        </button>

                        <button
                          onClick={() => handleGenerateResume(selectedItem.job._id)}
                          disabled={generatingResumeId === selectedItem.job._id}
                          className="p-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5 transition-all cursor-pointer disabled:opacity-50"
                          title="Regenerate tailored resume"
                        >
                          {generatingResumeId === selectedItem.job._id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                          ) : (
                            <RefreshCw className="w-4 h-4" />
                          )}
                        </button>

                        <a
                          href={jobsApi.getResumeDownloadUrl(selectedItem.job._id)}
                          download
                          className="p-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5 transition-all"
                          title="Download tailored Word document (.docx)"
                        >
                          <Download className="w-4 h-4" />
                        </a>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4 space-y-3">
                      <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                        Synthesize your candidate profile JSON directly with {selectedItem.job.company}'s requirements to generate an ATS-optimized resume stored against this job match listing.
                      </p>
                      <button
                        onClick={() => handleGenerateResume(selectedItem.job._id, true)}
                        disabled={generatingResumeId === selectedItem.job._id}
                        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition-all cursor-pointer disabled:opacity-50"
                      >
                        {generatingResumeId === selectedItem.job._id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        {generatingResumeId === selectedItem.job._id ? "Synthesizing Resume with AI…" : "Generate Tailored Resume"}
                      </button>
                    </div>
                  )}
                </div>

                {/* 4. Job Description & Responsibilities */}
                {selectedItem.job.description && (
                  <div className="glass rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-bold text-white">Job Description</h3>
                      <button
                        onClick={() => setDescExpanded(!descExpanded)}
                        className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold cursor-pointer"
                      >
                        {descExpanded ? "Collapse" : "Expand All"}
                      </button>
                    </div>

                    <div
                      className={`text-xs text-slate-300 whitespace-pre-wrap leading-relaxed overflow-hidden transition-all ${
                        descExpanded ? "max-h-none" : "max-h-52 relative"
                      }`}
                    >
                      {selectedItem.job.description}
                      {!descExpanded && (
                        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-slate-950 to-transparent pointer-events-none" />
                      )}
                    </div>

                    {!descExpanded && (
                      <button
                        onClick={() => setDescExpanded(true)}
                        className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 cursor-pointer"
                      >
                        Read full job description <ChevronRight className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          ) : (
            <div className="glass rounded-2xl p-10 text-center">
              <Briefcase className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-semibold text-white">Select a job to view details</p>
              <p className="text-xs text-slate-400 mt-1">Click on any matched opening on the left to inspect its compatibility breakdown and apply.</p>
            </div>
          )}
        </div>
      </div>

      {/* ── TAILORED RESUME PREVIEW MODAL ── */}
      <AnimatePresence>
        {previewModalOpen && previewItem && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl glass border border-white/10 shadow-2xl overflow-hidden bg-slate-950/95 my-auto"
            >
              {/* Modal Header */}
              <div className="p-4 sm:p-5 border-b border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white/[0.02]">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      {previewItem.tailored_resume?.template === "classic_ats" ? "Classic ATS Template" : "Default Template (Google Doc)"}
                    </span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Tailored for {previewItem.job.company}
                    </span>
                  </div>
                  <h3 className="text-base sm:text-lg font-bold text-white truncate">
                    Tailored Resume: {previewItem.job.title}
                  </h3>
                </div>

                {/* Tabs & Controls */}
                <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                  <div className="flex items-center p-1 rounded-xl bg-white/5 border border-white/10">
                    <button
                      onClick={() => setPreviewTab("doc")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        previewTab === "doc"
                          ? "bg-purple-600 text-white shadow-md shadow-purple-600/20"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <FileText className="w-3.5 h-3.5" />
                      <span>Document Preview</span>
                    </button>
                    <button
                      onClick={() => setPreviewTab("json")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        previewTab === "json"
                          ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/20"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <FileCode className="w-3.5 h-3.5" />
                      <span>Tailored JSON</span>
                    </button>
                  </div>

                  <button
                    onClick={() => setPreviewModalOpen(false)}
                    className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-6 custom-scrollbar bg-slate-900/50">
                {previewTab === "doc" ? (
                  /* ── DOCUMENT PREVIEW TAB ── */
                  <div className="max-w-2xl mx-auto bg-slate-950 text-slate-200 border border-white/15 rounded-xl shadow-2xl p-6 sm:p-8 space-y-6">
                    {/* Header: Candidate Info */}
                    <div className="text-center border-b border-white/10 pb-5">
                      <h1 className="text-xl sm:text-2xl font-black text-white tracking-wide">
                        {previewItem.tailored_resume?.personal?.name ||
                          previewItem.tailored_resume?.personal?.full_name ||
                          previewItem.tailored_resume?.personal?.fullName ||
                          "Candidate Name"}
                      </h1>
                      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 mt-2 text-xs text-slate-400">
                        {previewItem.tailored_resume?.personal?.email && (
                          <span>{previewItem.tailored_resume.personal.email}</span>
                        )}
                        {previewItem.tailored_resume?.personal?.phone && (
                          <>
                            <span>•</span>
                            <span>{previewItem.tailored_resume.personal.phone}</span>
                          </>
                        )}
                        {formatLocation(previewItem.tailored_resume?.personal?.location) && (
                          <>
                            <span>•</span>
                            <span>{formatLocation(previewItem.tailored_resume?.personal?.location)}</span>
                          </>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 mt-1 text-xs text-indigo-400">
                        {previewItem.tailored_resume?.personal?.linkedin && (
                          <span>{previewItem.tailored_resume.personal.linkedin}</span>
                        )}
                        {previewItem.tailored_resume?.personal?.github && (
                          <>
                            <span>•</span>
                            <span>{previewItem.tailored_resume.personal.github}</span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Tailored Professional Summary */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400">
                          Professional Summary
                        </h2>
                        <span className="text-[10px] text-purple-300 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20">
                          AI-Tailored for {previewItem.job.company}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed bg-white/[0.02] p-3 rounded-lg border border-white/5">
                        {previewItem.tailored_resume?.tailored_summary || previewItem.tailored_resume?.summary || "Experienced software engineer dedicated to building robust and performant systems."}
                      </p>
                    </div>

                    {/* Technical Skills & Core Competencies */}
                    <div>
                      <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-2">
                        Core Competencies & Skills
                      </h2>
                      {previewItem.tailored_resume?.skills && typeof previewItem.tailored_resume.skills === "object" && !Array.isArray(previewItem.tailored_resume.skills) ? (
                        <div className="space-y-2 text-xs">
                          {Object.entries(previewItem.tailored_resume.skills).map(([category, skillList]) => (
                            <div key={category} className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-2">
                              <span className="font-semibold text-slate-300 sm:w-28 shrink-0 capitalize">{category}:</span>
                              <div className="flex flex-wrap gap-1 flex-1">
                                {(skillList as string[]).map((sk) => {
                                  const isMatching = (previewItem.tailored_resume?.matching_skills || []).some(
                                    (m) => m.toLowerCase() === sk.toLowerCase()
                                  );
                                  return (
                                    <span
                                      key={sk}
                                      className={`px-1.5 py-0.5 rounded text-[11px] ${
                                        isMatching
                                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-medium"
                                          : "bg-white/5 text-slate-400 border border-white/5"
                                      }`}
                                    >
                                      {sk}
                                    </span>
                                  );
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {((previewItem.tailored_resume?.skills as string[]) || []).map((sk) => (
                            <span key={sk} className="px-2 py-0.5 rounded text-xs bg-white/5 text-slate-300 border border-white/10">
                              {sk}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Work Experience */}
                    {previewItem.tailored_resume?.experience && previewItem.tailored_resume.experience.length > 0 && (
                      <div>
                        <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-3">
                          Professional Experience
                        </h2>
                        <div className="space-y-4">
                          {previewItem.tailored_resume.experience.map((exp, idx) => (
                            <div key={idx} className="border-l-2 border-purple-500/40 pl-3">
                              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs">
                                <span className="font-bold text-white text-sm">{exp.title}</span>
                                <span className="text-slate-400 text-[11px]">
                                  {exp.start_date} – {exp.current ? "Present" : exp.end_date}
                                </span>
                              </div>
                              <div className="text-xs text-indigo-300 font-medium">
                                {exp.company} {formatLocation(exp.location) && `• ${formatLocation(exp.location)}`}
                              </div>
                              {exp.description && (
                                <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">{exp.description}</p>
                              )}
                              {exp.highlights && exp.highlights.length > 0 && (
                                <ul className="mt-1.5 space-y-1 list-disc list-inside text-xs text-slate-400">
                                  {exp.highlights.map((h, hidx) => (
                                    <li key={hidx} className="leading-relaxed">{h}</li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Projects */}
                    {previewItem.tailored_resume?.projects && previewItem.tailored_resume.projects.length > 0 && (
                      <div>
                        <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-2">
                          Featured Projects
                        </h2>
                        <div className="space-y-3">
                          {previewItem.tailored_resume.projects.map((proj, pidx) => (
                            <div key={pidx} className="bg-white/[0.02] p-3 rounded-lg border border-white/5 text-xs">
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-bold text-white">{proj.title}</span>
                                {proj.link && (
                                  <a href={proj.link} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 text-[11px]">
                                    View <ExternalLink className="w-2.5 h-2.5" />
                                  </a>
                                )}
                              </div>
                              {proj.description && (
                                <p className="text-slate-300 text-xs mt-1 leading-relaxed">{proj.description}</p>
                              )}
                              {proj.tech_stack && proj.tech_stack.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2">
                                  {proj.tech_stack.map((t) => (
                                    <span key={t} className="px-1.5 py-0.2 rounded text-[10px] bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                                      {t}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Education */}
                    {previewItem.tailored_resume?.education && previewItem.tailored_resume.education.length > 0 && (
                      <div>
                        <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-2">
                          Education
                        </h2>
                        <div className="space-y-2">
                          {previewItem.tailored_resume.education.map((edu, eidx) => (
                            <div key={eidx} className="flex items-center justify-between text-xs">
                              <div>
                                <span className="font-semibold text-white">{edu.degree} {edu.field && `in ${edu.field}`}</span>
                                <div className="text-slate-400 text-[11px]">{edu.institution}</div>
                              </div>
                              <span className="text-slate-400 text-[11px]">{edu.year}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  /* ── TAILORED JSON TAB ── */
                  <div className="space-y-3">
                    <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-indigo-300">
                      <div>
                        <p className="font-semibold text-white">Stored against Job-User Match Listing</p>
                        <p className="text-[11px] text-slate-400">
                          MongoDB collection: <code className="text-indigo-300">db.job_matches.tailored_resume</code>
                        </p>
                      </div>
                      <button
                        onClick={() => handleCopyJson(previewItem.tailored_resume)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all cursor-pointer self-start sm:self-auto"
                      >
                        {copiedJson ? <Check className="w-3.5 h-3.5 text-emerald-300" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedJson ? "Copied JSON!" : "Copy JSON"}</span>
                      </button>
                    </div>

                    <pre className="p-4 rounded-xl bg-black/80 border border-white/10 text-emerald-400 font-mono text-xs overflow-x-auto leading-relaxed max-h-[60vh] custom-scrollbar selection:bg-emerald-500/30">
                      {JSON.stringify(previewItem.tailored_resume, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="p-4 border-t border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white/[0.02]">
                <button
                  onClick={() => setPreviewModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-400 hover:text-white text-xs font-semibold transition-all cursor-pointer"
                >
                  Close
                </button>

                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => handleGenerateResume(previewItem.job._id, true)}
                    disabled={generatingResumeId === previewItem.job._id}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
                  >
                    {generatingResumeId === previewItem.job._id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    <span>Regenerate</span>
                  </button>

                  <a
                    href={jobsApi.getResumeDownloadUrl(previewItem.job._id)}
                    download
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold transition-all"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download .docx</span>
                  </a>

                  <button
                    onClick={() => {
                      handleApply(previewItem.job._id);
                      setPreviewModalOpen(false);
                    }}
                    disabled={applying === previewItem.job._id || ["APPLIED", "VERIFIED_SUCCESS"].includes(previewItem.application?.status || "")}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all cursor-pointer disabled:opacity-50"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Auto-Apply with this Resume</span>
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 flex items-center justify-center text-slate-500 text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-indigo-500" /> Loading jobs…
        </div>
      }
    >
      <JobsPageContent />
    </Suspense>
  );
}
