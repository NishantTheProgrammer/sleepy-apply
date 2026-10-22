"use client";
import { useEffect, useState, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, MapPin, Building2, Zap, CheckCircle, Loader2, Sparkles,
  ExternalLink, Search, Check, AlertTriangle, FileText, ChevronRight,
  SlidersHorizontal, ChevronLeft, Award, Globe, ShieldCheck, X
} from "lucide-react";
import { jobsApi } from "@/lib/api";

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
  job: {
    _id: string;
    title: string;
    company: string;
    location: string;
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

  // Filtered jobs list
  const filteredJobs = useMemo(() => {
    return jobs.filter((item) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        item.job.title.toLowerCase().includes(q) ||
        item.job.company.toLowerCase().includes(q) ||
        (item.job.location && item.job.location.toLowerCase().includes(q));

      if (!matchesSearch) return false;

      if (filterTab === "high") {
        return item.compatibility_score >= 75;
      }
      if (filterTab === "remote") {
        return item.job.is_remote || (item.job.location && item.job.location.toLowerCase().includes("remote"));
      }
      if (filterTab === "bengaluru") {
        return (
          item.job.location &&
          (item.job.location.toLowerCase().includes("bengaluru") ||
            item.job.location.toLowerCase().includes("bangalore"))
        );
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
                              <MapPin className="w-3 h-3 text-slate-500" /> {item.job.location || "Bengaluru, India"}
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
                      <MapPin className="w-3.5 h-3.5 text-slate-500" /> {selectedItem.job.location || "Remote"}
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
                <div className="glass rounded-2xl p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-purple-400" />
                      <h3 className="text-sm font-bold text-white">AI Tailored Resume Variant</h3>
                    </div>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      ATS Score: 94
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed mb-3">
                    Targeted keywords prioritized:{" "}
                    <span className="text-slate-200 font-medium">
                      {selectedItem.matching_skills.slice(0, 5).join(", ")}
                    </span>
                  </p>
                  <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 text-[11px] text-slate-400 font-mono">
                    <p className="text-indigo-300 font-semibold mb-1">Tailored Profile Summary:</p>
                    Candidate profile structured for {selectedItem.job.company}'s engineering standards with emphasis on distributed backend reliability and full-stack performance.
                  </div>
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
