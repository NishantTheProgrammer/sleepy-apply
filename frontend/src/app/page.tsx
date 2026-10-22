"use client";
import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { motion } from "framer-motion";
import { Bot, Briefcase, FileText, Zap, ShieldCheck, AlertCircle } from "lucide-react";

const FEATURES = [
  { icon: FileText, label: "AI Profile Builder",      desc: "Upload your resume, AI fills the rest" },
  { icon: Briefcase, label: "Smart Job Discovery",    desc: "Auto-fetches matching jobs continuously" },
  { icon: Zap,       label: "Auto Applications",      desc: "Applies with a tailored resume per job" },
  { icon: Bot,       label: "Discord Notifications",  desc: "Updates you on every step" },
];

function LoginContent() {
  const { user, loading, login, devLogin } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  useEffect(() => {
    if (!loading && user) router.replace("/user/dashboard");
  }, [user, loading, router]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-16">
      {/* Wordmark */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-10"
      >
        <h1 className="text-5xl font-black gradient-text mb-3">Sleepy Apply</h1>
        <p className="text-slate-400 text-lg max-w-md">
          Set it up once. Get hired while you sleep.
        </p>
      </motion.div>

      {error && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 p-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2 max-w-md"
        >
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Authentication was interrupted. Try logging in again below.</span>
        </motion.div>
      )}

      {/* Feature grid */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.15 }}
        className="grid grid-cols-2 gap-3 mb-10 max-w-lg w-full"
      >
        {FEATURES.map(({ icon: Icon, label, desc }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 * i + 0.2 }}
            className="glass rounded-2xl p-4"
          >
            <Icon className="w-5 h-5 text-indigo-400 mb-2" />
            <p className="text-sm font-semibold text-white">{label}</p>
            <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
          </motion.div>
        ))}
      </motion.div>

      {/* Login CTAs */}
      <div className="flex flex-col items-center gap-3 w-full max-w-xs">
        <motion.button
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3 }}
          onClick={login}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 px-8 py-3.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm transition-all shadow-lg shadow-indigo-600/40 hover:shadow-indigo-600/60 hover:-translate-y-0.5 active:scale-95 disabled:opacity-50 cursor-pointer"
        >
          {/* Discord icon */}
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z" />
          </svg>
          Continue with Discord
        </motion.button>

        <motion.button
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.35 }}
          onClick={devLogin}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-6 py-2.5 rounded-2xl bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 text-xs font-semibold transition-all hover:-translate-y-0.5 active:scale-95 disabled:opacity-50 cursor-pointer"
        >
          <ShieldCheck className="w-4 h-4 text-purple-400" />
          Quick Admin Sign-In (Dev Mode)
        </motion.button>
      </div>

      <p className="text-xs text-slate-600 mt-6 text-center max-w-xs">
        We only read your Discord username and avatar. Your credentials are encrypted and never exposed.
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}
