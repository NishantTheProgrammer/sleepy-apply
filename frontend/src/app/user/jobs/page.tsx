"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Briefcase, MapPin, Building2, Zap, CheckCircle, Loader2, Sparkles } from "lucide-react";
import { jobsApi } from "@/lib/api";

interface JobItem {
  _id: string;
  job: { _id: string; title: string; company: string; location: string; is_remote: boolean; application_url: string };
  compatibility_score: number;
  matching_skills: string[];
  missing_skills: string[];
  application?: { status: string };
}

const STATUS_STYLE: Record<string, string> = {
  VERIFIED_SUCCESS: "text-emerald-300 bg-emerald-400/10 border-emerald-400/20",
  APPLIED:          "text-blue-300 bg-blue-400/10 border-blue-400/20",
  APPLYING:         "text-yellow-300 bg-yellow-400/10 border-yellow-400/20",
  FAILED:           "text-red-300 bg-red-400/10 border-red-400/20",
  REQUIRES_USER_ACTION: "text-orange-300 bg-orange-400/10 border-orange-400/20",
};

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState("");

  const load = async (p = 1) => {
    setLoading(true);
    try {
      const res = await jobsApi.list({ page: p, limit: 20 });
      setJobs(res.items as JobItem[]);
      setTotal(res.total);
      setPage(p);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDiscoverJobs = async () => {
    setDiscovering(true);
    setDiscoverMsg("");
    try {
      const res = await jobsApi.fetchNow();
      setDiscoverMsg(res.message || "Discovery started! Matching jobs to your profile…");
      setTimeout(() => load(1), 3000);
      setTimeout(() => load(1), 6000);
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
      load(page);
    } catch (e) {
      console.error(e);
    } finally {
      setApplying(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Matched Jobs</h1>
          <p className="text-slate-500 text-sm mt-1">{total} jobs matched to your profile · sorted by compatibility</p>
        </div>
        <button
          onClick={handleDiscoverJobs}
          disabled={discovering}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 cursor-pointer self-start sm:self-auto"
        >
          {discovering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
          {discovering ? "Discovering & Matching…" : "Discover Jobs Now"}
        </button>
      </div>

      {discoverMsg && (
        <div className="mb-6 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0 text-indigo-400" />
          <span>{discoverMsg}</span>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center items-center py-20 gap-2 text-slate-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading jobs…
        </div>
      ) : jobs.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center">
          <Briefcase className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <h3 className="text-sm font-bold text-white mb-1">No matched jobs yet</h3>
          <p className="text-slate-400 text-xs max-w-sm mx-auto mb-5 leading-relaxed">
            Trigger our AI discovery pipeline to scrape active tech postings, enrich requirements, and score them against your profile.
          </p>
          <button
            onClick={handleDiscoverJobs}
            disabled={discovering}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 cursor-pointer"
          >
            {discovering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {discovering ? "Discovering & Matching…" : "Fetch & Match Jobs Now"}
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {jobs.map((item, i) => {
            const score = item.compatibility_score;
            const appStatus = item.application?.status;
            return (
              <motion.div
                key={item._id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="glass glass-hover rounded-2xl p-5"
              >
                <div className="flex items-start gap-4">
                  {/* Score ring */}
                  <div className="shrink-0 flex flex-col items-center">
                    <span className={`text-2xl font-black ${score >= 75 ? "score-high" : score >= 50 ? "score-medium" : "score-low"}`}>
                      {score}
                    </span>
                    <span className="text-[9px] text-slate-500 uppercase tracking-wider">match</span>
                  </div>

                  {/* Job info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-bold text-white text-sm">{item.job.title}</h3>
                        <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-400 flex-wrap">
                          <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{item.job.company}</span>
                          <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{item.job.location || (item.job.is_remote ? "Remote" : "—")}</span>
                        </div>
                      </div>
                      {appStatus && (
                        <span className={`shrink-0 text-[10px] px-2 py-0.5 rounded border font-semibold ${STATUS_STYLE[appStatus] ?? "text-slate-400 bg-white/5 border-white/10"}`}>
                          {appStatus.replace(/_/g, " ")}
                        </span>
                      )}
                    </div>

                    {/* Skills */}
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {item.matching_skills.slice(0, 5).map((s) => (
                        <span key={s} className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">{s}</span>
                      ))}
                      {item.missing_skills.slice(0, 3).map((s) => (
                        <span key={s} className="px-1.5 py-0.5 rounded text-[10px] bg-red-500/10 text-red-300 border border-red-500/20">{s}</span>
                      ))}
                    </div>

                    {/* Actions */}
                    <div className="mt-3 flex items-center gap-2">
                      <a
                        href={item.job.application_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs px-3 py-1.5 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:bg-white/5 transition-all"
                      >
                        View Job
                      </a>
                      {!["APPLIED", "APPLYING", "VERIFIED_SUCCESS"].includes(appStatus ?? "") && (
                        <button
                          onClick={() => handleApply(item.job._id)}
                          disabled={applying === item.job._id}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all shadow-sm shadow-indigo-600/30 disabled:opacity-50"
                        >
                          {applying === item.job._id
                            ? <><Loader2 className="w-3 h-3 animate-spin" /> Applying…</>
                            : <><Zap className="w-3 h-3" /> Apply</>}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
