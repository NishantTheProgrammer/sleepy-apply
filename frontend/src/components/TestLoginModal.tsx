"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  X, Sparkles, Check, ArrowRight, Loader2,
  ShieldCheck, MapPin, Briefcase, Code2, Users
} from "lucide-react";
import { authApi, TestPersona } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface TestLoginModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function TestLoginModal({ isOpen, onClose }: TestLoginModalProps) {
  const router = useRouter();
  const { refresh } = useAuth();
  const [personas, setPersonas] = useState<TestPersona[]>([]);
  const [loading, setLoading] = useState(true);
  const [switchingId, setSwitchingId] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    let mounted = true;
    const fetchPersonas = async () => {
      setLoading(true);
      try {
        const res = await authApi.getTestPersonas();
        if (mounted) setPersonas(res.personas || []);
      } catch (err) {
        console.error("Failed to load test personas", err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchPersonas();
    return () => {
      mounted = false;
    };
  }, [isOpen]);

  const handleSelectPersona = async (personaId: string) => {
    setSwitchingId(personaId);
    try {
      await authApi.testLogin(personaId);
      await refresh();
      onClose();
      // Navigate to jobs to immediately see tailored matches
      router.push("/user/jobs");
      router.refresh();
    } catch (err) {
      console.error("Test login failed", err);
      alert(err instanceof Error ? err.message : "Failed to switch persona");
    } finally {
      setSwitchingId(null);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="relative w-full max-w-4xl rounded-3xl bg-slate-900 border border-white/10 shadow-2xl p-6 sm:p-8 z-10 max-h-[90vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-4 pb-5 border-b border-white/10 shrink-0">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                  <Sparkles className="w-3 h-3" /> QA & Algorithm Testing Tool
                </span>
                <span className="text-xs text-slate-400">
                  {personas.length > 0 ? `${personas.length} Candidate Profiles` : "Candidate Profiles"}
                </span>
              </div>
              <h2 className="text-xl sm:text-2xl font-black text-white">Select a Test Candidate Profile</h2>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Click any candidate below to instantly sign in and evaluate domain-aware matching, score breakdown, and resume tailoring.
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Persona Grid Content */}
          <div className="flex-1 overflow-y-auto py-5 pr-1 space-y-4">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
                <p className="text-xs text-slate-400">Loading test candidate profiles…</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {personas.map((p) => {
                  const isSwitching = switchingId === p.id;
                  const skillsList = Object.values(p.skills || {}).flat().slice(0, 4);

                  const badgeStyles: Record<string, string> = {
                    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
                    blue: "bg-blue-500/10 text-blue-400 border-blue-500/30",
                    cyan: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
                    amber: "bg-amber-500/10 text-amber-400 border-amber-500/30",
                    purple: "bg-purple-500/10 text-purple-400 border-purple-500/30",
                    rose: "bg-rose-500/10 text-rose-400 border-rose-500/30",
                  };

                  const avatarBg: Record<string, string> = {
                    emerald: "from-emerald-500 to-teal-600",
                    blue: "from-blue-500 to-indigo-600",
                    cyan: "from-cyan-500 to-blue-600",
                    amber: "from-amber-500 to-orange-600",
                    purple: "from-purple-500 to-pink-600",
                    rose: "from-rose-500 to-red-600",
                  };

                  return (
                    <motion.div
                      key={p.id}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => !switchingId && handleSelectPersona(p.id)}
                      className={`group relative flex flex-col justify-between p-4 rounded-2xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/10 hover:border-indigo-500/50 transition-all cursor-pointer ${isSwitching ? "ring-2 ring-indigo-500 bg-indigo-500/10" : ""
                        }`}
                    >
                      {/* Top bar with Avatar and Badge */}
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-3">
                          <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${avatarBg[p.badge_color] || "from-indigo-500 to-purple-600"} flex items-center justify-center text-white font-black text-sm shadow-md`}>
                            {p.avatar_letter}
                          </div>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeStyles[p.badge_color] || "bg-white/10 text-slate-300 border-white/10"}`}>
                            {p.category}
                          </span>
                        </div>

                        {/* Name & Target Title */}
                        <h3 className="font-bold text-sm text-white group-hover:text-indigo-300 transition-colors">
                          {p.name}
                        </h3>
                        <p className="text-xs text-slate-300 font-medium mt-0.5 line-clamp-1">
                          {p.title}
                        </p>

                        <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mt-1.5">
                          <MapPin className="w-3 h-3 text-slate-500 shrink-0" />
                          <span>{p.location}</span>
                        </div>

                        {/* Summary */}
                        <p className="text-[11px] text-slate-400 mt-2.5 line-clamp-2 leading-relaxed">
                          {p.summary}
                        </p>
                      </div>

                      {/* Bottom Skills & Action */}
                      <div className="mt-4 pt-3 border-t border-white/5">
                        <div className="flex flex-wrap gap-1 mb-3">
                          {skillsList.map((skill, skIdx) => (
                            <span
                              key={`${p.id}-${skill}-${skIdx}`}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-white/5 border border-white/10 text-slate-300 font-mono"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>

                        <button
                          disabled={isSwitching}
                          className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-indigo-600/30 group-hover:bg-indigo-600 text-indigo-300 group-hover:text-white text-xs font-semibold border border-indigo-500/40 group-hover:border-indigo-500 transition-all cursor-pointer"
                        >
                          {isSwitching ? (
                            <>
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              Signing In…
                            </>
                          ) : (
                            <>
                              Sign In as {p.name.split(" ")[0]}
                              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                            </>
                          )}
                        </button>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="pt-4 border-t border-white/10 flex items-center justify-between text-xs text-slate-500 shrink-0">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              Temporary development feature for multi-candidate testing
            </span>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white transition-colors cursor-pointer"
            >
              Close
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}

