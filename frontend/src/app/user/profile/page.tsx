"use client";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, User, CheckCircle, HelpCircle, Loader2 } from "lucide-react";
import { profileApi } from "@/lib/api";

interface Question { id: string; question: string; field: string }

export default function ProfilePage() {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const [p, q] = await Promise.all([profileApi.get(), profileApi.getQuestions()]);
    setProfile(p.profile);
    setQuestions(q.questions as Question[]);
  };

  useEffect(() => { load(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg("");
    try {
      const res = await profileApi.uploadResume(file);
      setUploadMsg(res.message);
      setTimeout(load, 2000);
    } catch (err: unknown) {
      setUploadMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleAnswers = async () => {
    setSaving(true);
    try {
      await profileApi.submitAnswers(
        Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer }))
      );
      setAnswers({});
      load();
    } finally {
      setSaving(false);
    }
  };

  const completion = (profile?.completion_score as number) ?? 0;

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-3xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-black gradient-text">Profile</h1>
        <p className="text-slate-500 text-sm mt-1">Your professional identity powering every application</p>
      </div>

      {/* Completion bar */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass rounded-2xl p-5 mb-5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-semibold text-white">Profile Completeness</span>
          </div>
          <span className={`text-sm font-black ${completion >= 75 ? "score-high" : completion >= 50 ? "score-medium" : "score-low"}`}>
            {completion}%
          </span>
        </div>
        <div className="h-2 bg-white/10 rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${completion}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="h-full rounded-full"
            style={{ background: `linear-gradient(90deg, rgb(var(--theme-c1)), rgb(var(--theme-c2)))` }}
          />
        </div>
      </motion.div>

      {/* Resume upload */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-5 mb-5">
        <div className="flex items-center gap-2 mb-3">
          <Upload className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">Upload Resume</h2>
        </div>
        <p className="text-xs text-slate-400 mb-4">
          Upload a PDF — AI will extract your profile. Existing data won&apos;t be overwritten without review.
        </p>
        <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleUpload} />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-all shadow-lg shadow-indigo-600/30 disabled:opacity-50"
        >
          {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {uploading ? "Analyzing…" : "Choose PDF"}
        </button>
        {uploadMsg && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-xs text-emerald-400 mt-3 flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5" /> {uploadMsg}
          </motion.p>
        )}
        {Boolean(profile?.resume_filename) && (
          <p className="text-xs text-slate-500 mt-2">Current: {String(profile?.resume_filename)}</p>
        )}
      </motion.div>

      {/* AI Questions */}
      <AnimatePresence>
        {questions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass rounded-2xl p-5 mb-5"
            style={{ border: "1px solid rgba(var(--theme-c1), 0.3)" }}
          >
            <div className="flex items-center gap-2 mb-4">
              <HelpCircle className="w-4 h-4 text-yellow-400" />
              <h2 className="font-bold text-sm text-white">AI needs more info</h2>
              <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-yellow-400/15 text-yellow-300 border border-yellow-400/20">
                {questions.length} question{questions.length > 1 ? "s" : ""}
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {questions.map((q) => (
                <div key={q.id}>
                  <label className="text-xs text-slate-300 mb-1.5 block">{q.question}</label>
                  <input
                    type="text"
                    value={answers[q.id] ?? ""}
                    onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                    placeholder="Your answer…"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors"
                  />
                </div>
              ))}
            </div>
            <button
              onClick={handleAnswers}
              disabled={saving || Object.keys(answers).length === 0}
              className="mt-4 flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-all disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              Submit Answers
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Profile preview */}
      {profile && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-2xl p-5">
          <h2 className="font-bold text-sm text-white mb-4">Your Profile</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            {["full_name", "email", "phone", "location"].map((f) => (
              <div key={f}>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{f.replace("_", " ")}</p>
                <p className="text-slate-200">{((profile.personal as Record<string, string>)?.[f]) || "—"}</p>
              </div>
            ))}
          </div>
          {((profile.skills as string[]) ?? []).length > 0 && (
            <div className="mt-4">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Skills</p>
              <div className="flex flex-wrap gap-1.5">
                {(profile.skills as string[]).map((s) => (
                  <span key={s} className="px-2 py-0.5 rounded-md text-xs bg-indigo-500/15 text-indigo-300 border border-indigo-500/20">{s}</span>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
