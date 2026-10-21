"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Users, Briefcase, Zap, Activity } from "lucide-react";
import { adminApi } from "@/lib/api";

export default function AdminPage() {
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);

  useEffect(() => { adminApi.stats().then(setStats as (v: unknown) => void); }, []);

  const cards = stats
    ? [
        { label: "Active Users",       value: stats.users,              icon: Users,    color: "bg-indigo-500/15 text-indigo-400" },
        { label: "Active Jobs",         value: stats.active_jobs,        icon: Briefcase, color: "bg-emerald-500/15 text-emerald-400" },
        { label: "Total Applications",  value: stats.total_applications, icon: Zap,       color: "bg-yellow-500/15 text-yellow-400" },
        { label: "Active Workflows",    value: stats.active_workflows,   icon: Activity,  color: "bg-purple-500/15 text-purple-400" },
      ]
    : [];

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-black gradient-text">Admin Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Platform-wide overview</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        {cards.map(({ label, value, icon: Icon, color }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
              <div className={`p-2 rounded-xl ${color}`}><Icon className="w-4 h-4" /></div>
            </div>
            <p className="text-3xl font-black text-white">{String(value ?? "—")}</p>
          </motion.div>
        ))}
      </div>

      {/* Status breakdown */}
      {Boolean(stats?.application_status_breakdown) && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }} className="glass rounded-2xl p-5">
          <h2 className="font-bold text-sm text-white mb-4">Application Status Breakdown</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {Object.entries((stats?.application_status_breakdown as Record<string, number>) ?? {}).map(([status, count]) => (
              <div key={status} className="rounded-xl p-3" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}>
                <p className="text-2xl font-black text-white">{count}</p>
                <p className="text-[10px] text-slate-500 mt-0.5 uppercase tracking-wider">{status.replace(/_/g, " ")}</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
