"use client";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles, CheckCircle2, MessageSquare, ChevronRight, Loader2,
  RefreshCw, Check, ArrowRight, UserCheck, HelpCircle, Briefcase, Plus
} from "lucide-react";
import { profileApi, ScreeningData, ScreeningQuestion, ScreeningQAItem } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface ResumeScreeningQAProps {
  onProfileUpdated?: () => void;
}

export default function ResumeScreeningQA({ onProfileUpdated }: ResumeScreeningQAProps) {
  const { user, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ScreeningData | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>("");
  const [customRoleInput, setCustomRoleInput] = useState<string>("");
  const [isAddingCustom, setIsAddingCustom] = useState(false);
  const [roleChanging, setRoleChanging] = useState(false);

  // Question answers state: { [questionId]: answerText }
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [expandedQA, setExpandedQA] = useState(true);

  const loadScreening = async () => {
    if (!user) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const res = await profileApi.getScreening();
      setData(res);
      setSelectedRole(res.selected_role || (res.target_roles.length > 0 ? res.target_roles[0] : ""));
      // Pre-fill answers from any existing QA history
      const initialAnswers: Record<string, string> = {};
      (res.qa_history || []).forEach((item) => {
        initialAnswers[item.id] = item.answer;
      });
      setAnswers(initialAnswers);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!msg.includes("Invalid or expired token") && !msg.includes("401")) {
        console.warn("Failed to load screening data", err);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading && user) {
      void loadScreening();
    } else if (!authLoading && !user) {
      setLoading(false);
    }
  }, [authLoading, user?.id]);

  const handleSelectRole = async (role: string) => {
    if (role === selectedRole || roleChanging) return;
    setRoleChanging(true);
    setSelectedRole(role);
    setIsAddingCustom(false);
    try {
      const res = await profileApi.selectScreeningRole(role);
      setData((prev) => prev ? { ...prev, selected_role: res.selected_role, questions: res.questions } : prev);
      if (onProfileUpdated) onProfileUpdated();
    } catch (err) {
      console.error("Failed to select role", err);
    } finally {
      setRoleChanging(false);
    }
  };

  const handleAddCustomRole = async () => {
    const trimmed = customRoleInput.trim();
    if (!trimmed) return;
    await handleSelectRole(trimmed);
    setCustomRoleInput("");
  };

  const handleOptionClick = (questionId: string, option: string) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: option,
    }));
  };

  const handleSubmitAnswers = async () => {
    if (!data || submitting) return;
    setSubmitting(true);
    setSubmitSuccess(false);
    try {
      const answerPayload = data.questions
        .filter((q) => answers[q.id] && answers[q.id].trim().length > 0)
        .map((q) => ({
          question_id: q.id,
          question: q.question,
          answer: answers[q.id].trim(),
          category: q.category,
        }));

      if (answerPayload.length === 0) {
        alert("Please answer at least one screening question.");
        setSubmitting(false);
        return;
      }

      const res = await profileApi.submitScreeningAnswers(answerPayload, selectedRole);
      setData((prev) => prev ? { ...prev, qa_history: res.qa_history } : prev);
      setSubmitSuccess(true);
      setTimeout(() => setSubmitSuccess(false), 4000);
      if (onProfileUpdated) onProfileUpdated();
    } catch (err) {
      console.error("Failed to save answers", err);
      alert(err instanceof Error ? err.message : "Failed to submit answers");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegenerate = async () => {
    if (regenerating) return;
    setRegenerating(true);
    try {
      const res = await profileApi.regenerateScreeningQuestions(selectedRole);
      setData((prev) => prev ? { ...prev, questions: res.questions } : prev);
    } catch (err) {
      console.error("Regenerate failed", err);
    } finally {
      setRegenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="glass rounded-3xl p-6 sm:p-8 mb-8 flex flex-col items-center justify-center py-12 gap-3 border border-indigo-500/20">
        <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
        <p className="text-xs text-slate-400">Analyzing resume & preparing dynamic recruiter screening…</p>
      </div>
    );
  }

  if (!data) return null;

  const totalAnswered = data.questions.filter((q) => answers[q.id]?.trim()).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-6 sm:p-8 mb-8 border border-indigo-500/30 relative overflow-hidden shadow-2xl"
    >
      {/* Background Glow */}
      <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-transparent blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-white/10 relative z-10">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Sparkles className="w-3 h-3" /> AI Screening & Knowledge Base
            </span>
            <span className="text-xs text-slate-400">Fast Local Model Q/A</span>
          </div>
          <h2 className="text-lg sm:text-xl font-black text-white flex items-center gap-2">
            Dynamic Candidate Screening & Profile Alignment
          </h2>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-2xl">
            Based on your uploaded resume, confirm your target role and answer recruiter screening questions. Your answers are stored against your profile to boost matching scores and tailor submissions.
          </p>
        </div>

        <button
          onClick={handleRegenerate}
          disabled={regenerating || roleChanging}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 text-xs font-semibold transition-all shrink-0 cursor-pointer disabled:opacity-50"
          title="Regenerate questions with fast local AI"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${regenerating ? "animate-spin text-indigo-400" : ""}`} />
          <span>{regenerating ? "Generating…" : "Refresh Questions"}</span>
        </button>
      </div>

      {/* ── STEP 1: TARGET PROFILE SELECTION (CHIPS) ── */}
      <div className="py-6 border-b border-white/10 relative z-10">
        <div className="flex items-center justify-between gap-2 mb-3">
          <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Briefcase className="w-3.5 h-3.5 text-indigo-400" />
            1. Select Which Profile You Are Applying For:
          </label>
          {roleChanging && (
            <span className="text-xs text-indigo-400 flex items-center gap-1 animate-pulse">
              <Loader2 className="w-3 h-3 animate-spin" /> Adapting screening questions…
            </span>
          )}
        </div>

        {/* Chips list */}
        <div className="flex flex-wrap gap-2 items-center">
          {(data.target_roles || []).map((role) => {
            const isSelected = selectedRole.toLowerCase() === role.toLowerCase();
            return (
              <button
                key={role}
                onClick={() => handleSelectRole(role)}
                disabled={roleChanging}
                className={`px-3.5 py-2 rounded-xl text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer ${
                  isSelected
                    ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-500/25 ring-2 ring-indigo-400/50"
                    : "bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 hover:border-white/20"
                }`}
              >
                {isSelected && <Check className="w-3.5 h-3.5" />}
                <span>{role}</span>
              </button>
            );
          })}

          {/* Add custom role button / input */}
          {isAddingCustom ? (
            <div className="flex items-center gap-1.5 bg-white/5 p-1 rounded-xl border border-white/15">
              <input
                type="text"
                value={customRoleInput}
                onChange={(e) => setCustomRoleInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddCustomRole()}
                placeholder="e.g. Lead SRE Engineer"
                autoFocus
                className="bg-transparent text-xs text-white px-2.5 py-1 focus:outline-none placeholder:text-slate-500 w-44"
              />
              <button
                onClick={handleAddCustomRole}
                className="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
              >
                Set
              </button>
              <button
                onClick={() => setIsAddingCustom(false)}
                className="px-2 py-1 text-xs text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
          ) : (
            <button
              onClick={() => setIsAddingCustom(true)}
              className="px-3 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-indigo-300 bg-white/[0.02] hover:bg-white/5 border border-dashed border-white/20 hover:border-indigo-400/40 transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Other Role…</span>
            </button>
          )}
        </div>
      </div>

      {/* ── STEP 2: DYNAMIC RECRUITER QUESTIONS ── */}
      <div className="py-6 relative z-10 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <MessageSquare className="w-3.5 h-3.5 text-purple-400" />
              2. Technical & Recruiter Screening Questions for:{" "}
              <span className="text-indigo-400 normal-case font-bold">{selectedRole}</span>
            </label>
            <p className="text-xs text-slate-400 mt-0.5">
              Click any quick prefill chip or type your custom answer.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-400 bg-white/5 px-2.5 py-1 rounded-lg border border-white/10">
            {totalAnswered} / {data.questions.length} answered
          </span>
        </div>

        <div className="space-y-4">
          {data.questions.map((q, idx) => {
            const currentAns = answers[q.id] || "";
            const isFilled = currentAns.trim().length > 0;

            return (
              <motion.div
                key={q.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className={`p-4 sm:p-5 rounded-2xl border transition-all ${
                  isFilled
                    ? "bg-white/[0.04] border-indigo-500/40 shadow-sm"
                    : "bg-white/[0.02] border-white/10 hover:border-white/20"
                }`}
              >
                {/* Question title and context */}
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex items-start gap-2.5">
                    <span className="w-5 h-5 rounded-full bg-indigo-500/20 text-indigo-300 text-[11px] font-black flex items-center justify-center shrink-0 mt-0.5 border border-indigo-500/30">
                      {idx + 1}
                    </span>
                    <div>
                      <h3 className="text-sm font-bold text-white leading-snug">
                        {q.question}
                      </h3>
                      {q.context_hint && (
                        <p className="text-[11px] text-slate-400 mt-1 flex items-center gap-1.5">
                          <HelpCircle className="w-3 h-3 text-slate-500 shrink-0" />
                          <span>{q.context_hint}</span>
                        </p>
                      )}
                    </div>
                  </div>
                  {isFilled && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20 shrink-0">
                      <Check className="w-3 h-3" /> Answered
                    </span>
                  )}
                </div>

                {/* Suggested options chips */}
                {q.suggested_options && q.suggested_options.length > 0 && (
                  <div className="mt-3 mb-2 flex flex-wrap gap-1.5">
                    {q.suggested_options.map((opt) => {
                      const isOptionSelected = currentAns.trim() === opt.trim();
                      return (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => handleOptionClick(q.id, opt)}
                          className={`px-2.5 py-1 rounded-lg text-xs transition-all cursor-pointer text-left ${
                            isOptionSelected
                              ? "bg-indigo-600 text-white font-semibold shadow-md shadow-indigo-600/30 ring-1 ring-white/20"
                              : "bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10"
                          }`}
                        >
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Answer input area */}
                <div className="mt-2.5">
                  <input
                    type="text"
                    value={currentAns}
                    onChange={(e) =>
                      setAnswers((prev) => ({
                        ...prev,
                        [q.id]: e.target.value,
                      }))
                    }
                    placeholder="Type or customize your answer…"
                    className="w-full bg-slate-950/60 border border-white/10 focus:border-indigo-500 rounded-xl px-3.5 py-2 text-xs text-white placeholder:text-slate-600 focus:outline-none transition-all"
                  />
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Submit Actions */}
        <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-white/10">
          <div className="text-xs text-slate-400">
            {submitSuccess && (
              <span className="text-emerald-400 font-semibold flex items-center gap-1.5 animate-pulse">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Answers saved to your MongoDB candidate profile! Re-scoring matched jobs…
              </span>
            )}
          </div>

          <button
            onClick={handleSubmitAnswers}
            disabled={submitting || totalAnswered === 0}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-bold transition-all shadow-lg shadow-indigo-600/30 disabled:opacity-50 cursor-pointer"
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving to Profile…
              </>
            ) : (
              <>
                <UserCheck className="w-4 h-4" />
                Save Q&A & Update Profile
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── STEP 3: PERSISTED Q&A REPOSITORY ── */}
      {data.qa_history && data.qa_history.length > 0 && (
        <div className="mt-4 pt-5 border-t border-white/10 relative z-10">
          <button
            onClick={() => setExpandedQA((prev) => !prev)}
            className="w-full flex items-center justify-between text-left text-xs font-bold uppercase tracking-wider text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              Saved Candidate Q&A Knowledge Base ({data.qa_history.length})
            </span>
            <span className="text-[11px] text-slate-500">
              {expandedQA ? "Hide ▲" : "Show ▼"}
            </span>
          </button>

          {expandedQA && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
              {data.qa_history.map((item) => (
                <div
                  key={item.id}
                  className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1"
                >
                  <p className="text-xs font-semibold text-slate-300 line-clamp-2">
                    {item.question}
                  </p>
                  <p className="text-xs font-medium text-emerald-300">
                    "{item.answer}"
                  </p>
                  {item.target_role && (
                    <span className="inline-block text-[10px] text-slate-500 mt-1">
                      Role: {item.target_role}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

