"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Cpu, Key, Bell, Zap, CheckCircle, X, Loader2, ChevronDown } from "lucide-react";
import { settingsApi } from "@/lib/api";

const PROVIDERS = ["ollama", "openai", "gemini", "anthropic"] as const;
type Provider = typeof PROVIDERS[number];

const PROVIDER_LABELS: Record<Provider, string> = {
  ollama: "Ollama (Local)",
  openai: "OpenAI",
  gemini: "Google Gemini",
  anthropic: "Anthropic",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string; response?: string } | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([settingsApi.get(), settingsApi.getModelSuggestions()]).then(([s, m]) => {
      setSettings(s as Record<string, unknown>);
      setModels(m as Record<string, string[]>);
      setForm({
        ai_provider: (s as Record<string, unknown>).ai_provider ?? "ollama",
        ai_model: (s as Record<string, unknown>).ai_model ?? "llama3.2:1b",
      });
    });
  }, []);

  const provider = (form.ai_provider ?? "ollama") as Provider;
  const isOllama = provider === "ollama";

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await settingsApi.update(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
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
    } finally {
      setTesting(false);
    }
  };

  const field = (key: string, value: unknown) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-black gradient-text">Settings</h1>
        <p className="text-slate-500 text-sm mt-1">Configure your AI provider and application preferences</p>
      </div>

      {/* AI Provider */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-5 mb-4">
        <div className="flex items-center gap-2 mb-4">
          <Cpu className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">AI Provider</h2>
        </div>

        {/* Provider selector */}
        <div className="grid grid-cols-2 gap-2 mb-4">
          {PROVIDERS.map((p) => (
            <button
              key={p}
              onClick={() => { field("ai_provider", p); field("ai_model", models[p]?.[0] ?? ""); }}
              className={`px-3 py-2.5 rounded-xl text-xs font-semibold border transition-all ${
                provider === p
                  ? "bg-indigo-600/30 border-indigo-500/50 text-indigo-200"
                  : "border-white/10 text-slate-400 hover:text-white hover:border-white/20"
              }`}
            >
              {PROVIDER_LABELS[p]}
            </button>
          ))}
        </div>

        {/* Ollama: base URL */}
        {isOllama && (
          <div className="mb-3">
            <label className="text-xs text-slate-400 block mb-1.5">Ollama Base URL</label>
            <input
              type="url"
              placeholder="http://localhost:11434"
              onChange={(e) => field("ai_base_url", e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors"
            />
            <p className="text-[10px] text-slate-500 mt-1">
              {settings?.ai_base_url_set ? "✓ URL configured" : "Not configured yet"}
            </p>
          </div>
        )}

        {/* API key (non-Ollama) */}
        {!isOllama && (
          <div className="mb-3">
            <label className="text-xs text-slate-400 block mb-1.5">API Key</label>
            <input
              type="password"
              placeholder={settings?.ai_api_key_set ? "••••••••••••••••" : "sk-..."}
              onChange={(e) => field("ai_api_key", e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors"
            />
            <p className="text-[10px] text-slate-500 mt-1">
              {settings?.ai_api_key_set ? "✓ Key configured (encrypted at rest)" : "Not configured yet"}
            </p>
          </div>
        )}

        {/* Model selector */}
        <div className="mb-4">
          <label className="text-xs text-slate-400 block mb-1.5">Model</label>
          <div className="relative">
            <select
              value={form.ai_model as string ?? ""}
              onChange={(e) => field("ai_model", e.target.value)}
              className="w-full appearance-none bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50 transition-colors pr-8"
            >
              {(models[provider] ?? []).map((m) => (
                <option key={m} value={m} className="bg-slate-900">{m}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none" />
          </div>
        </div>

        {/* Test connection */}
        <div className="flex items-center gap-3">
          <button
            onClick={testAI}
            disabled={testing}
            className="flex items-center gap-2 px-3 py-2 rounded-xl border border-white/10 text-slate-300 hover:text-white hover:border-white/20 text-xs font-semibold transition-all disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Test Connection
          </button>
          {testResult && (
            <span className={`flex items-center gap-1 text-xs font-semibold ${testResult.ok ? "text-emerald-400" : "text-red-400"}`}>
              {testResult.ok ? <CheckCircle className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
              {testResult.ok ? "Connected" : testResult.error}
            </span>
          )}
        </div>
      </motion.div>

      {/* Auto-apply prefs */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-2xl p-5 mb-4">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="w-4 h-4 text-indigo-400" />
          <h2 className="font-bold text-sm text-white">Application Preferences</h2>
        </div>
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-sm text-white font-medium">Auto-apply</p>
            <p className="text-xs text-slate-500">Apply automatically when score meets threshold</p>
          </div>
          <button
            onClick={() => field("application_preferences", { ...((form.application_preferences as Record<string, unknown>) ?? {}), auto_apply: !(form.application_preferences as Record<string, unknown>)?.auto_apply })}
            className={`relative w-11 h-6 rounded-full transition-colors ${(form.application_preferences as Record<string, unknown>)?.auto_apply ? "bg-indigo-600" : "bg-white/10"}`}
          >
            <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${(form.application_preferences as Record<string, unknown>)?.auto_apply ? "left-5.5 translate-x-0.5" : "left-0.5"}`} />
          </button>
        </div>
      </motion.div>

      {/* Save */}
      <button
        onClick={save}
        disabled={saving}
        className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-600/30 disabled:opacity-50"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4" /> : <Key className="w-4 h-4" />}
        {saved ? "Saved!" : saving ? "Saving…" : "Save Settings"}
      </button>
    </div>
  );
}
