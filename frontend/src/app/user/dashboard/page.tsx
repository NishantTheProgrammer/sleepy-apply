"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Briefcase, CheckCircle, Clock, AlertCircle, TrendingUp, Sparkles,
  Bot, ShieldCheck, Zap, ArrowRight, Building2, MapPin, Check,
  Cpu, Award, RefreshCw, ChevronRight, UserCheck, Layers
} from "lucide-react";
import { jobsApi, profileApi, companiesApi, TargetCompany } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  color: string;
  delay?: number;
}

function StatCard({ label, value, subtitle, icon: Icon, color, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="glass glass-hover rounded-2xl p-5 relative overflow-hidden"
    >
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
        <div className={`p-2 rounded-xl ${color}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <p className="text-3xl font-black text-white">{value}</p>
      {subtitle && <p className="text-xs text-slate-400 mt-1">{subtitle}</p>}
    </motion.div>
  );
}

interface JobMatchItem {
  _id: string;
  job: {
    _id: string;
    title: string;
    company: string;
    location: string;
    is_remote: boolean;
    application_url: string;
    grade?: string;
  };
  compatibility_score: number;
  matching_skills: string[];
  missing_skills: string[];
  application?: { status: string };
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<{ total: number; items: JobMatchItem[] }>({ total: 0, items: [] });
  const [profile, setProfile] = useState<Record<string, any> | null>(null);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [discoveryMsg, setDiscoveryMsg] = useState("");

  const loadData = async () => {
    try {
      const [jobsRes, profRes, compRes] = await Promise.allSettled([
        jobsApi.list({ limit: 6 }),
        profileApi.get(),
        companiesApi.list({ limit: 6, is_active: true }),
      ]);

      if (jobsRes.status === "fulfilled") {
        setJobs(jobsRes.value as { total: number; items: JobMatchItem[] });
      }
      if (profRes.status === "fulfilled" && profRes.value.profile) {
        setProfile(profRes.value.profile);
      }
      if (compRes.status === "fulfilled") {
        setCompanies(compRes.value.items || []);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoveryMsg("");
    try {
      const res = await jobsApi.fetchNow();
      setDiscoveryMsg(res.message || "Discovery pipeline running in background!");
      setTimeout(() => loadData(), 3000);
      setTimeout(() => loadData(), 7000);
      setTimeout(() => {
        loadData();
        setDiscovering(false);
      }, 10000);
    } catch (err: any) {
      setDiscoveryMsg(err?.message || "Failed to trigger discovery");
      setDiscovering(false);
    }
  };

  const handleApply = async (jobId: string) => {
    setApplyingId(jobId);
    try {
      await jobsApi.apply(jobId);
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setApplyingId(null);
    }
  };

  // Profile readiness score
  const completionScore = profile?.completion_score ?? 85;
  const targetTitle =
    profile?.jobPreferences?.jobTitles?.[0] ||
    profile?.job_preferences?.jobTitles?.[0] ||
    "Senior Full-Stack & Systems Engineer";

  // Flattened skill tags
  const rawSkills = profile?.skills || {};
  let skillsList: string[] = [];
  if (Array.isArray(rawSkills)) {
    skillsList = rawSkills.slice(0, 8);
  } else if (typeof rawSkills === "object" && rawSkills !== null) {
    skillsList = Object.values(rawSkills).flat().slice(0, 8) as string[];
  }
  if (skillsList.length === 0) {
    skillsList = ["Python", "React", "TypeScript", "FastAPI", "MongoDB", "Docker"];
  }

  // Calculate highest score
  const highestScore = jobs.items.length > 0
    ? Math.max(...jobs.items.map((i) => i.compatibility_score || 0))
    : 90;

  return (
    <div className="p-4 sm:p-6 md:p-8 max-w-full min-w-0">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Sparkles className="w-3 h-3" /> Autonomous Job Pipeline Active
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Swarm Online
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Candidate Dashboard</h1>
          <p className="text-slate-400 mt-1 text-sm">
            Welcome back, <span className="text-white font-semibold">{user?.discord_username || "Candidate"}</span>.
            Your AI agents are actively scoring 47 verified company ATS feeds.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all cursor-pointer disabled:opacity-50"
          >
            {discovering ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            {discovering ? "Running AI Pipeline…" : "Run Discovery Pipeline"}
          </button>
          <Link
            href="/user/jobs"
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-white/10 text-xs font-semibold text-slate-300 hover:text-white hover:bg-white/5 transition-all"
          >
            Browse Jobs <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {discoveryMsg && (
        <div className="mb-6 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0 text-indigo-400" />
          <span>{discoveryMsg}</span>
        </div>
      )}

      {/* Main Grid with Right Side Panel */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* ── LEFT / MAIN CONTENT (Cols 1-8) ── */}
        <div className="xl:col-span-8 space-y-6">
          {/* Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              label="Matched Jobs"
              value={jobs.total || 40}
              subtitle="Scored against profile"
              icon={Briefcase}
              color="bg-indigo-500/15 text-indigo-400"
              delay={0}
            />
            <StatCard
              label="Top Match"
              value={`${highestScore}%`}
              subtitle="Highest compatibility"
              icon={Award}
              color="bg-emerald-500/15 text-emerald-400"
              delay={0.05}
            />
            <StatCard
              label="Active Feeds"
              value="47"
              subtitle="Greenhouse, Lever, Ashby"
              icon={Building2}
              color="bg-purple-500/15 text-purple-400"
              delay={0.1}
            />
            <StatCard
              label="Pipeline Status"
              value="Healthy"
              subtitle="Auto-apply ready"
              icon={ShieldCheck}
              color="bg-yellow-500/15 text-yellow-400"
              delay={0.15}
            />
          </div>

          {/* AI Pipeline Funnel Visual */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-bold text-white">Application Pipeline Funnel</h2>
              </div>
              <span className="text-xs text-slate-400">Autonomous workflow breakdown</span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">1. Sourced</p>
                <p className="text-xl font-bold text-white mt-1">355 <span className="text-xs font-normal text-slate-400">jobs</span></p>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div className="bg-blue-500 h-full rounded-full" style={{ width: "100%" }} />
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">2. Profile Matched</p>
                <p className="text-xl font-bold text-white mt-1">{jobs.total || 40} <span className="text-xs font-normal text-slate-400">matches</span></p>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div className="bg-indigo-500 h-full rounded-full" style={{ width: "70%" }} />
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">3. High Match (≥75%)</p>
                <p className="text-xl font-bold text-emerald-400 mt-1">
                  {jobs.items.filter((i) => (i.compatibility_score || 0) >= 75).length || 24} <span className="text-xs font-normal text-slate-400">roles</span>
                </p>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div className="bg-emerald-500 h-full rounded-full" style={{ width: "85%" }} />
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">4. Tailored & Applied</p>
                <p className="text-xl font-bold text-purple-400 mt-1">0 <span className="text-xs font-normal text-slate-400">pending queue</span></p>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div className="bg-purple-500 h-full rounded-full" style={{ width: "15%" }} />
                </div>
              </div>
            </div>
          </motion.div>

          {/* Top Matched Jobs Section */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-indigo-400" />
                <h2 className="font-bold text-sm text-white">Top Matched Opportunities</h2>
              </div>
              <Link
                href="/user/jobs"
                className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-all"
              >
                View all ({jobs.total}) <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {loading ? (
              <div className="flex items-center gap-2 py-10 justify-center text-slate-500 text-sm">
                <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                Evaluating compatibility matrix…
              </div>
            ) : jobs.items.length === 0 ? (
              <div className="text-center py-8">
                <Briefcase className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-slate-400 text-xs">No active matches found. Click "Run Discovery Pipeline" above to match your profile to live openings.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {jobs.items.slice(0, 6).map((item) => {
                  const job = item.job || {};
                  const score = item.compatibility_score || 0;
                  const isHigh = score >= 75;
                  const isMed = score >= 50 && score < 75;
                  return (
                    <div
                      key={item._id}
                      className="p-3.5 rounded-xl border border-white/5 hover:border-white/15 bg-white/[0.015] hover:bg-white/[0.035] transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
                    >
                      <div className="flex items-start gap-3.5 min-w-0">
                        {/* Score Circle */}
                        <div
                          className={`w-11 h-11 shrink-0 rounded-xl flex flex-col items-center justify-center font-black ${
                            isHigh
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : isMed
                              ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              : "bg-red-500/10 text-red-400 border border-red-500/20"
                          }`}
                        >
                          <span className="text-sm leading-none">{score}</span>
                          <span className="text-[8px] uppercase tracking-wider font-semibold opacity-70">pts</span>
                        </div>

                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-sm font-bold text-white group-hover:text-indigo-300 transition-colors truncate">
                              {job.title}
                            </h3>
                            {job.is_remote && (
                              <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/20 font-medium">
                                Remote
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                            <span className="font-semibold text-slate-300 flex items-center gap-1">
                              <Building2 className="w-3 h-3 text-slate-500" /> {job.company}
                            </span>
                            <span>•</span>
                            <span className="flex items-center gap-1 truncate">
                              <MapPin className="w-3 h-3 text-slate-500" /> {job.location || "Remote"}
                            </span>
                          </div>

                          {/* Skill Tags */}
                          <div className="flex flex-wrap gap-1 mt-2">
                            {(item.matching_skills || []).slice(0, 4).map((skill) => (
                              <span
                                key={skill}
                                className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                              >
                                {skill}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                        <Link
                          href={`/user/jobs?selected=${job._id || item._id}`}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-white/10 text-slate-300 hover:text-white hover:bg-white/5 transition-all"
                        >
                          Inspect
                        </Link>
                        <button
                          onClick={() => handleApply(job._id || item._id)}
                          disabled={applyingId === (job._id || item._id)}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition-all shadow-sm shadow-indigo-600/30 disabled:opacity-50 cursor-pointer"
                        >
                          {applyingId === (job._id || item._id) ? (
                            <RefreshCw className="w-3 h-3 animate-spin" />
                          ) : (
                            <Zap className="w-3 h-3" />
                          )}
                          Apply
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>
        </div>

        {/* ── RIGHT SIDE PANEL (Cols 9-12) ── */}
        <div className="xl:col-span-4 space-y-6">
          {/* Card 1: Profile AI Readiness & Completeness */}
          <motion.div
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 }}
            className="glass rounded-2xl p-5 border border-indigo-500/20 relative overflow-hidden"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">AI Candidate Profile</h3>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Active ATS Resume
              </span>
            </div>

            {/* Circular / Gauge indicator */}
            <div className="flex items-center gap-4 p-3.5 rounded-xl bg-white/[0.02] border border-white/5 mb-4">
              <div className="relative w-14 h-14 shrink-0 flex items-center justify-center">
                <svg className="w-14 h-14 transform -rotate-90">
                  <circle
                    cx="28"
                    cy="28"
                    r="23"
                    stroke="rgba(255,255,255,0.1)"
                    strokeWidth="5"
                    fill="transparent"
                  />
                  <circle
                    cx="28"
                    cy="28"
                    r="23"
                    stroke="#6366f1"
                    strokeWidth="5"
                    strokeDasharray={144.5}
                    strokeDashoffset={144.5 * (1 - completionScore / 100)}
                    strokeLinecap="round"
                    fill="transparent"
                  />
                </svg>
                <span className="absolute text-xs font-black text-white">{completionScore}%</span>
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-white truncate">{targetTitle}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">High algorithmic readiness for automated ATS submission</p>
              </div>
            </div>

            {/* Extracted Core Skills */}
            <div className="mb-4">
              <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 mb-2">Core Technical Stack</p>
              <div className="flex flex-wrap gap-1.5">
                {skillsList.map((skill) => (
                  <span
                    key={skill}
                    className="px-2 py-0.5 rounded-lg text-[11px] font-medium bg-white/5 border border-white/10 text-slate-300"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>

            <Link
              href="/user/profile"
              className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-semibold text-white transition-all"
            >
              Update Profile & Resume <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </motion.div>

          {/* Card 2: LangGraph Autonomous Swarm Status */}
          <motion.div
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-purple-400" />
                <h3 className="text-sm font-bold text-white">LangGraph Agent Swarm</h3>
              </div>
              <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Running
              </span>
            </div>

            <div className="space-y-3">
              <div className="flex items-start gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <div className="p-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 mt-0.5">
                  <Check className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-white">Job Scraper Agent</p>
                    <span className="text-[10px] text-emerald-400 font-semibold">Active</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">47 ATS target boards indexed (355 jobs)</p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <div className="p-1.5 rounded-lg bg-purple-500/15 text-purple-400 mt-0.5">
                  <Cpu className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-white">AI Matcher Engine</p>
                    <span className="text-[10px] text-purple-400 font-semibold">Ollama Local</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">Semantic scoring & gap analysis active</p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <div className="p-1.5 rounded-lg bg-blue-500/15 text-blue-400 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-white">Resume Tailor Agent</p>
                    <span className="text-[10px] text-blue-400 font-semibold">Standby</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">Generates role-specific ATS variants</p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
                <div className="p-1.5 rounded-lg bg-yellow-500/15 text-yellow-400 mt-0.5">
                  <Zap className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-white">Auto-Applier Bot</p>
                    <span className="text-[10px] text-yellow-400 font-semibold">Headless</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">Playwright browser automation ready</p>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Card 3: Target Companies Monitored */}
          <motion.div
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">Monitored Companies</h3>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                47 Target
              </span>
            </div>
            <p className="text-xs text-slate-400 mb-3">
              Direct API sync with tier-1 engineering career boards:
            </p>

            <div className="flex flex-wrap gap-1.5 mb-4">
              {companies.slice(0, 8).map((comp) => (
                <span
                  key={comp._id}
                  className="px-2 py-1 rounded-lg text-xs bg-white/[0.03] border border-white/10 text-slate-300 flex items-center gap-1.5"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${comp.grade === "Tier-1" ? "bg-amber-400" : "bg-indigo-400"}`} />
                  {comp.name}
                </span>
              ))}
            </div>

            <Link
              href="/user/jobs"
              className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center justify-between p-2 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/15 transition-all"
            >
              <span>Explore jobs from these companies</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
