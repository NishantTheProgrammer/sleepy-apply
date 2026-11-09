"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Cpu, Key, Bell, Zap, CheckCircle, X, Loader2, ChevronDown,
  Sliders, Sparkles, Shield, Target, FileText, Check, AlertCircle,
  Bot, Send, MessageSquare
} from "lucide-react";
import { settingsApi } from "@/lib/api";

const PROVIDERS = ["ollama", "openai", "gemini", "anthropic"] as const;
type Provider = typeof PROVIDERS[number];

const PROVIDER_LABELS: Record<Provider, string> = {
  ollama: "Ollama (Local / Free)",
  openai: "OpenAI",
  gemini: "Google Gemini",
  anthropic: "Anthropic",
};

interface AppPreferences {
  auto_apply?: boolean;
  auto_apply_threshold?: number;
  min_compatibility_score?: number;
  tailoring_temperature?: number;
  extraction_temperature?: number;
  bold_matching_keywords?: boolean;
  max_bullets_per_role?: number;
  filter_irrelevant_projects?: boolean;
  max_tailored_projects?: number;
  require_confirmation?: boolean;
  daily_apply_limit?: number;
}

interface NotificationPreferences {
  discord_dm?: boolean;
  discord_webhook_url?: string;
  email?: boolean;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [discordStatus, setDiscordStatus] = useState<{
    bot_configured: boolean;
    bot_connected: boolean;
    global_webhook_configured: boolean;
    user_webhook_configured: boolean;
    user_discord_linked: boolean;
    user_discord_id: string | null;
    user_discord_username: string | null;
  } | null>(null);

  const [form, setForm] = useState<Record<string, unknown>>({
    notification_preferences: {
      discord_dm: true,
      discord_webhook_url: "",
      email: false,
    },
    application_preferences: {
      auto_apply: false,
      auto_apply_threshold: 70,
      min_compatibility_score: 70,
      tailoring_temperature: 0.2,
      extraction_temperature: 0.1,
      bold_matching_keywords: true,
      max_bullets_per_role: 5,
      filter_irrelevant_projects: true,
      max_tailored_projects: 3,
      require_confirmation: true,
      daily_apply_limit: 5,
    },
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string; response?: string } | null>(null);
  const [testingDiscord, setTestingDiscord] = useState(false);
  const [discordTestResult, setDiscordTestResult] = useState<{ ok: boolean; message?: string; error?: string } | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([
      settingsApi.get(),
      settingsApi.getModelSuggestions(),
      settingsApi.getDiscordStatus().catch(() => null),
    ]).then(([s, m, dStatus]) => {
      const sDoc = (s as Record<string, unknown>) ?? {};
      setSettings(sDoc);
      setModels((m as Record<string, string[]>) ?? {});
      if (dStatus) setDiscordStatus(dStatus);

      const existingPrefs = (sDoc.application_preferences as AppPreferences) ?? {};
      const existingNotif = (sDoc.notification_preferences as NotificationPreferences) ?? {};

      setForm({
        ai_provider: sDoc.ai_provider ?? "ollama",
        ai_model: sDoc.ai_model ?? "qwen2.5-coder:14b",
        ai_base_url: "",
        ai_api_key: "",
        notification_preferences: {
          discord_dm: existingNotif.discord_dm !== false,
          discord_webhook_url: existingNotif.discord_webhook_url || "",
          email: Boolean(existingNotif.email),
        },
        application_preferences: {
          auto_apply: Boolean(existingPrefs.auto_apply),
          auto_apply_threshold: Number(existingPrefs.auto_apply_threshold ?? existingPrefs.min_compatibility_score ?? 70),
          min_compatibility_score: Number(existingPrefs.min_compatibility_score ?? existingPrefs.auto_apply_threshold ?? 70),
          tailoring_temperature: Number(existingPrefs.tailoring_temperature ?? 0.2),
          extraction_temperature: Number(existingPrefs.extraction_temperature ?? 0.1),
          bold_matching_keywords: existingPrefs.bold_matching_keywords !== false,
          max_bullets_per_role: Number(existingPrefs.max_bullets_per_role ?? 5),
          filter_irrelevant_projects: existingPrefs.filter_irrelevant_projects !== false,
          max_tailored_projects: Number(existingPrefs.max_tailored_projects ?? 3),
          require_confirmation: existingPrefs.require_confirmation !== false,
          daily_apply_limit: Number(existingPrefs.daily_apply_limit ?? 5),
        },
      });
    });
  }, []);

  const provider = (form.ai_provider ?? "ollama") as Provider;
  const isOllama = provider === "ollama";
  const appPrefs = ((form.application_preferences as AppPreferences) ?? {}) as AppPreferences;
  const notifPrefs = ((form.notification_preferences as NotificationPreferences) ?? {}) as NotificationPreferences;

  const updateAppPref = (key: keyof AppPreferences, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      application_preferences: {
        ...((prev.application_preferences as Record<string, unknown>) ?? {}),
        [key]: value,
        ...(key === "auto_apply_threshold" ? { min_compatibility_score: value } : {}),
        ...(key === "min_compatibility_score" ? { auto_apply_threshold: value } : {}),
      },
    }));
  };

  const updateNotifPref = (key: keyof NotificationPreferences, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      notification_preferences: {
        ...((prev.notification_preferences as Record<string, unknown>) ?? {}),
        [key]: value,
      },
    }));
  };

  const testDiscord = async () => {
    setTestingDiscord(true);
    setDiscordTestResult(null);
    try {
      await settingsApi.update(form);
      const res = await settingsApi.testDiscord(notifPrefs.discord_webhook_url);
      setDiscordTestResult(res);
    } catch (err: unknown) {
      setDiscordTestResult({
        ok: false,
        error: err instanceof Error ? err.message : "Failed to trigger test notification",
      });
    } finally {
      setTestingDiscord(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await settingsApi.update(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  };

  const testAI = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await settingsApi.update(form);
      const res = await settingsApi.testAI();
      setTestResult(res as { ok: boolean; error?: string; response?: string });
    } catch (err: unknown) {
      setTestResult({ ok: false, error: err instanceof Error ? err.message : "Connection failed" });
    } finally {
      setTesting(false);
    }
  };

  const field = (key: string, value: unknown) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-black gradient-text">Settings</h1>
        <p className="text-slate-400 text-sm mt-1">Configure your AI models, auto-apply thresholds, and resume tailoring engine</p>
      </div>

      {/* AI Provider & Models */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Cpu className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">AI Provider & Core Model</h2>
        </div>

        {/* Provider selector */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          {PROVIDERS.map((p) => (
            <button
              key={p}
              onClick={() => { field("ai_provider", p); field("ai_model", models[p]?.[0] ?? ""); }}
              className={`px-3 py-2.5 rounded-xl text-xs font-semibold border transition-all text-center ${
                provider === p
                  ? "bg-indigo-600/30 border-indigo-500/50 text-indigo-200 shadow-sm shadow-indigo-500/20"
                  : "border-white/10 text-slate-400 hover:text-white hover:border-white/20"
              }`}
            >
              {PROVIDER_LABELS[p]}
            </button>
          ))}
        </div>

        {/* Ollama: base URL */}
        {isOllama && (
          <div className="mb-4">
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Ollama Base URL</label>
            <input
              type="url"
              placeholder="http://localhost:11434 (or host.docker.internal)"
              onChange={(e) => field("ai_base_url", e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              {settings?.ai_base_url_set ? "✓ Base URL configured" : "Defaults to http://host.docker.internal:11434"}
            </p>
          </div>
        )}

        {/* API key (non-Ollama) */}
        {!isOllama && (
          <div className="mb-4">
            <label className="text-xs text-slate-300 font-medium block mb-1.5">API Key</label>
            <input
              type="password"
              placeholder={settings?.ai_api_key_set ? "••••••••••••••••" : "Enter API key"}
              onChange={(e) => field("ai_api_key", e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              {settings?.ai_api_key_set ? "✓ Key safely encrypted at rest" : "Not configured yet"}
            </p>
          </div>
        )}

        {/* Model selector */}
        <div className="mb-4">
          <label className="text-xs text-slate-300 font-medium block mb-1.5">Default Model</label>
          <div className="relative">
            <select
              value={(form.ai_model as string) ?? ""}
              onChange={(e) => field("ai_model", e.target.value)}
              className="w-full appearance-none bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500/50 transition-colors pr-8"
            >
              {(models[provider] ?? []).map((m) => (
                <option key={m} value={m} className="bg-slate-900 text-white">{m}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            Recommended for local ATS extraction & coding: <strong className="text-indigo-300">qwen2.5-coder:14b</strong>
          </p>
        </div>

        {/* Test connection */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={testAI}
            disabled={testing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:border-white/20 text-xs font-semibold transition-all disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5 text-amber-400" />}
            Test AI Connection
          </button>
          {testResult && (
            <span className={`flex items-center gap-1.5 text-xs font-semibold ${testResult.ok ? "text-emerald-400" : "text-rose-400"}`}>
              {testResult.ok ? <CheckCircle className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
              {testResult.ok ? "Successfully Connected" : (testResult.error || "Connection failed")}
            </span>
          )}
        </div>
      </motion.div>

      {/* Auto-Apply & Job Matching Threshold */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Target className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">Auto-Apply & Matching Thresholds</h2>
        </div>

        {/* Auto-apply toggle */}
        <div className="flex items-center justify-between py-2 border-b border-white/5 pb-4 mb-4">
          <div>
            <p className="text-sm text-white font-medium">Automatic Job Application</p>
            <p className="text-xs text-slate-400">Trigger automatic application pipeline when job match score reaches your threshold</p>
          </div>
          <button
            onClick={() => updateAppPref("auto_apply", !appPrefs.auto_apply)}
            className={`relative w-12 h-6.5 rounded-full transition-colors ${appPrefs.auto_apply ? "bg-indigo-600" : "bg-white/10"}`}
          >
            <span className={`absolute top-0.5 w-5.5 h-5.5 bg-white rounded-full shadow transition-transform ${appPrefs.auto_apply ? "left-6" : "left-0.5"}`} />
          </button>
        </div>

        {/* Auto Apply Threshold Number */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs text-slate-300 font-medium">
              Auto-Apply Match Score Threshold (%):
            </label>
            <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              {appPrefs.auto_apply_threshold ?? 70}%
            </span>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="40"
              max="95"
              step="1"
              value={appPrefs.auto_apply_threshold ?? 70}
              onChange={(e) => updateAppPref("auto_apply_threshold", parseInt(e.target.value) || 70)}
              className="w-full accent-indigo-500 h-1.5 bg-white/10 rounded-lg cursor-pointer"
            />
            <input
              type="number"
              min="0"
              max="100"
              value={appPrefs.auto_apply_threshold ?? 70}
              onChange={(e) => updateAppPref("auto_apply_threshold", parseInt(e.target.value) || 70)}
              className="w-20 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-sm text-white font-semibold text-center focus:outline-none focus:border-indigo-500/50"
            />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            Jobs matching your profile at or above this percentage will qualify for auto-apply.
          </p>
        </div>

        {/* Daily Application Limit */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div>
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Daily Apply Limit</label>
            <input
              type="number"
              min="1"
              max="50"
              value={appPrefs.daily_apply_limit ?? 5}
              onChange={(e) => updateAppPref("daily_apply_limit", parseInt(e.target.value) || 5)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
            />
            <p className="text-[11px] text-slate-400 mt-1">Safety cap for submissions per day</p>
          </div>

          <div>
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Confirmation Before Apply</label>
            <div className="flex items-center justify-between h-10 px-3 bg-white/5 border border-white/10 rounded-xl">
              <span className="text-xs text-slate-300">Require User Confirmation</span>
              <button
                onClick={() => updateAppPref("require_confirmation", !appPrefs.require_confirmation)}
                className={`relative w-10 h-5.5 rounded-full transition-colors ${appPrefs.require_confirmation ? "bg-indigo-600" : "bg-white/10"}`}
              >
                <span className={`absolute top-0.5 w-4.5 h-4.5 bg-white rounded-full shadow transition-transform ${appPrefs.require_confirmation ? "left-5" : "left-0.5"}`} />
              </button>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Notify on Discord/Email before submitting</p>
          </div>
        </div>
      </motion.div>

      {/* AI Resume Tailoring & Extraction Tuning */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">Resume Tailoring & AI Parameters</h2>
        </div>

        {/* Tailoring Temperature */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs text-slate-300 font-medium">
              Tailoring Temperature:
            </label>
            <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/30">
              {Number(appPrefs.tailoring_temperature ?? 0.2).toFixed(2)}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="0.0"
              max="1.0"
              step="0.05"
              value={appPrefs.tailoring_temperature ?? 0.2}
              onChange={(e) => updateAppPref("tailoring_temperature", parseFloat(e.target.value) || 0.2)}
              className="w-full accent-amber-500 h-1.5 bg-white/10 rounded-lg cursor-pointer"
            />
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={appPrefs.tailoring_temperature ?? 0.2}
              onChange={(e) => updateAppPref("tailoring_temperature", parseFloat(e.target.value) || 0.2)}
              className="w-20 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-sm text-white font-semibold text-center focus:outline-none focus:border-amber-500/50"
            />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            <strong>0.1 – 0.3 recommended:</strong> Ultra-precise, zero-hallucination tailoring grounded strictly in your real work history. Higher values yield more creative phrasing.
          </p>
        </div>

        {/* Resume Extraction Temperature */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs text-slate-300 font-medium">
              Resume Extraction Temperature (Reading Uploads):
            </label>
            <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              {Number(appPrefs.extraction_temperature ?? 0.1).toFixed(2)}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="0.0"
              max="0.5"
              step="0.05"
              value={appPrefs.extraction_temperature ?? 0.1}
              onChange={(e) => updateAppPref("extraction_temperature", parseFloat(e.target.value) || 0.1)}
              className="w-full accent-emerald-500 h-1.5 bg-white/10 rounded-lg cursor-pointer"
            />
            <input
              type="number"
              min="0"
              max="0.5"
              step="0.05"
              value={appPrefs.extraction_temperature ?? 0.1}
              onChange={(e) => updateAppPref("extraction_temperature", parseFloat(e.target.value) || 0.1)}
              className="w-20 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-sm text-white font-semibold text-center focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            Controls factual fidelity when extracting past jobs, roles, and dates from uploaded resumes.
          </p>
        </div>

        {/* Max Bullets and Bold Keywords */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div>
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Max Bullets Per Experience</label>
            <input
              type="number"
              min="2"
              max="10"
              value={appPrefs.max_bullets_per_role ?? 5}
              onChange={(e) => updateAppPref("max_bullets_per_role", parseInt(e.target.value) || 5)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
            />
            <p className="text-[11px] text-slate-400 mt-1">Bullet points per job on tailored resumes</p>
          </div>

          <div>
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Bold Matching Skills</label>
            <div className="flex items-center justify-between h-10 px-3 bg-white/5 border border-white/10 rounded-xl">
              <span className="text-xs text-slate-300">Format keywords with **bold**</span>
              <button
                onClick={() => updateAppPref("bold_matching_keywords", !appPrefs.bold_matching_keywords)}
                className={`relative w-10 h-5.5 rounded-full transition-colors ${appPrefs.bold_matching_keywords ? "bg-indigo-600" : "bg-white/10"}`}
              >
                <span className={`absolute top-0.5 w-4.5 h-4.5 bg-white rounded-full shadow transition-transform ${appPrefs.bold_matching_keywords ? "left-5" : "left-0.5"}`} />
              </button>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Increases ATS recruiter scannability</p>
          </div>
        </div>

        {/* Project Relevance Filtering & Max Projects */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-white/5 mt-4">
          <div>
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Filter Irrelevant Projects</label>
            <div className="flex items-center justify-between h-10 px-3 bg-white/5 border border-white/10 rounded-xl">
              <span className="text-xs text-slate-300">Keep only matching projects</span>
              <button
                onClick={() => updateAppPref("filter_irrelevant_projects", !appPrefs.filter_irrelevant_projects)}
                className={`relative w-10 h-5.5 rounded-full transition-colors ${appPrefs.filter_irrelevant_projects !== false ? "bg-indigo-600" : "bg-white/10"}`}
              >
                <span className={`absolute top-0.5 w-4.5 h-4.5 bg-white rounded-full shadow transition-transform ${appPrefs.filter_irrelevant_projects !== false ? "left-5" : "left-0.5"}`} />
              </button>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Omits outdated, academic, or non-matching stack projects</p>
          </div>

          <div>
            <label className="text-xs text-slate-300 font-medium block mb-1.5">Max Tailored Projects</label>
            <input
              type="number"
              min="1"
              max="5"
              value={appPrefs.max_tailored_projects ?? 3}
              onChange={(e) => updateAppPref("max_tailored_projects", parseInt(e.target.value) || 3)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
            />
            <p className="text-[11px] text-slate-400 mt-1">Top relevant projects to highlight (2-3 recommended)</p>
          </div>
        </div>
      </motion.div>

      {/* Discord Notifications & Interactive Bot */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass rounded-2xl p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-indigo-400" />
            <h2 className="font-bold text-sm text-white">Discord Notifications & Interactive Bot</h2>
          </div>
          <div className="flex items-center gap-2">
            {discordStatus?.user_discord_linked ? (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                <CheckCircle className="w-3 h-3" /> @{discordStatus.user_discord_username}
              </span>
            ) : (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" /> Not Linked
              </span>
            )}
            {discordStatus?.bot_connected ? (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                ● Gateway Online
              </span>
            ) : discordStatus?.bot_configured ? (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                ● Bot Configured
              </span>
            ) : (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-500/10 text-slate-400 border border-slate-500/20">
                Webhook / REST
              </span>
            )}
          </div>
        </div>

        <p className="text-xs text-slate-400 mb-5">
          Get real-time alerts when applications are submitted, when action is required, and run two-way commands directly from Discord.
        </p>

        {/* Discord DM Toggle */}
        <div className="flex items-center justify-between p-3.5 bg-white/5 border border-white/10 rounded-xl mb-4">
          <div>
            <span className="text-xs font-medium text-white block">Discord Direct Messages (DMs)</span>
            <span className="text-[11px] text-slate-400">Receive private messages from the Sleepy Apply Bot for key application events</span>
          </div>
          <button
            onClick={() => updateNotifPref("discord_dm", !notifPrefs.discord_dm)}
            className={`relative w-10 h-5.5 rounded-full transition-colors ${notifPrefs.discord_dm ? "bg-indigo-600" : "bg-white/10"}`}
          >
            <span className={`absolute top-0.5 w-4.5 h-4.5 bg-white rounded-full shadow transition-transform ${notifPrefs.discord_dm ? "left-5" : "left-0.5"}`} />
          </button>
        </div>

        {/* Discord Webhook URL */}
        <div className="mb-5">
          <label className="text-xs text-slate-300 font-medium block mb-1.5">
            Channel Webhook URL (Optional)
          </label>
          <input
            type="text"
            placeholder="https://discord.com/api/webhooks/..."
            value={notifPrefs.discord_webhook_url || ""}
            onChange={(e) => updateNotifPref("discord_webhook_url", e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Broadcast job discoveries and submissions to your private Discord server channel.
          </p>
        </div>

        {/* Test Discord Notification Button */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={testDiscord}
            disabled={testingDiscord}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white font-medium text-xs transition-colors disabled:opacity-50"
          >
            {testingDiscord ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            {testingDiscord ? "Testing Discord…" : "Test Discord Notification"}
          </button>
          {discordTestResult && (
            <span
              className={`text-xs flex items-center gap-1.5 ${
                discordTestResult.ok ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {discordTestResult.ok ? <CheckCircle className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
              {discordTestResult.message || discordTestResult.error || "Completed"}
            </span>
          )}
        </div>

        {/* Two-Way Bot Commands Cheatsheet */}
        <div className="mt-5 p-4 rounded-xl bg-indigo-950/20 border border-indigo-500/20">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300 mb-2">
            <MessageSquare className="w-3.5 h-3.5" /> Interactive Bot Commands
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-slate-300">
            <div className="bg-black/30 p-2 rounded-lg border border-white/5">
              <code className="text-indigo-300 font-bold">!status</code> — Check profile & application pipeline stats
            </div>
            <div className="bg-black/30 p-2 rounded-lg border border-white/5">
              <code className="text-indigo-300 font-bold">!jobs</code> — View top 5 matched job openings
            </div>
            <div className="bg-black/30 p-2 rounded-lg border border-white/5">
              <code className="text-indigo-300 font-bold">!tailor &lt;job_id&gt;</code> — Tailor resume for a job
            </div>
            <div className="bg-black/30 p-2 rounded-lg border border-white/5">
              <code className="text-indigo-300 font-bold">!apply &lt;job_id&gt;</code> — Apply to job immediately
            </div>
            <div className="bg-black/30 p-2 rounded-lg border border-white/5 sm:col-span-2">
              <code className="text-indigo-300 font-bold">!profile</code> — Review verified skills, headline, & experience
            </div>
          </div>
        </div>
      </motion.div>

      {/* Save Button */}
      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-600/30 disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4" /> : <Key className="w-4 h-4" />}
          {saved ? "Settings Saved!" : saving ? "Saving…" : "Save All Settings"}
        </button>
        {saved && (
          <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
            <Check className="w-3.5 h-3.5" /> Applied to auto-apply & resume builder engine
          </span>
        )}
      </div>
    </div>
  );
}
