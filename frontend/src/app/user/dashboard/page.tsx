"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Briefcase, CheckCircle, Clock, AlertCircle, TrendingUp } from "lucide-react";
import { jobsApi, adminApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  delay?: number;
}

function StatCard({ label, value, icon: Icon, color, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="glass glass-hover rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
        <div className={`p-2 rounded-xl ${color}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <p className="text-3xl font-black text-white">{value}</p>
    </motion.div>
  );
}

const STATUS_COLOURS: Record<string, string> = {
  VERIFIED_SUCCESS: "text-emerald-400 bg-emerald-400/10",
  APPLIED:          "text-blue-400 bg-blue-400/10",
  APPLYING:         "text-yellow-400 bg-yellow-400/10",
  FAILED:           "text-red-400 bg-red-400/10",
  REQUIRES_USER_ACTION: "text-orange-400 bg-orange-400/10",
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<{ total: number; items: unknown[] }>({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    jobsApi.list({ limit: 5 }).then(setJobs).catch(console.error).finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-full min-w-0">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-black gradient-text">Dashboard</h1>
        <p className="text-slate-500 mt-1 text-sm">
          Welcome back, <span className="text-slate-300">{user?.discord_username}</span>
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        <StatCard label="Matched Jobs"   value={jobs.total}  icon={Briefcase}    color="bg-indigo-500/15 text-indigo-400" delay={0} />
        <StatCard label="Applied"        value="—"           icon={CheckCircle}  color="bg-emerald-500/15 text-emerald-400" delay={0.05} />
        <StatCard label="In Progress"    value="—"           icon={Clock}        color="bg-yellow-500/15 text-yellow-400" delay={0.1} />
        <StatCard label="Needs Action"   value="—"           icon={AlertCircle}  color="bg-orange-500/15 text-orange-400" delay={0.15} />
      </div>

      {/* Recent matched jobs */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass rounded-2xl p-5"
      >
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">Top Matched Jobs</h2>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-6 justify-center text-slate-500 text-sm">
            <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            Loading…
          </div>
        ) : jobs.items.length === 0 ? (
          <p className="text-slate-500 text-sm py-6 text-center">
            No jobs yet — set up your profile to start matching.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {(jobs.items as Record<string, unknown>[]).map((item) => {
              const job = item.job as Record<string, unknown>;
              const match = item as Record<string, unknown>;
              const score = match.compatibility_score as number;
              return (
                <div
                  key={job._id as string}
                  className="flex items-center gap-3 p-3 rounded-xl"
                  style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
                >
                  <div className={`text-lg font-black w-10 shrink-0 text-center ${score >= 75 ? "score-high" : score >= 50 ? "score-medium" : "score-low"}`}>
                    {score}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{job.title as string}</p>
                    <p className="text-xs text-slate-400">{job.company as string} · {job.location as string}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </motion.div>
    </div>
  );
}
