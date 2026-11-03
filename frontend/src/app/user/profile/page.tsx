"use client";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload, User, CheckCircle, HelpCircle, Loader2, Plus, Trash2,
  Briefcase, GraduationCap, Award, Globe, Save, Sparkles, X, ChevronDown, ChevronUp, MapPin,
  FileText, FileUp, AlertCircle
} from "lucide-react";
import { profileApi, templatesApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import ResumeTemplateSelector from "@/components/ResumeTemplateSelector";
import ResumeScreeningQA from "@/components/ResumeScreeningQA";

interface Question { id: string; question: string; field: string }

interface LocationData {
  address?: string;
  city?: string;
  postalCode?: string;
  country?: string;
}

interface PersonalData {
  fullName?: string;
  full_name?: string;
  email?: string;
  phone?: string;
  location?: LocationData | string;
  linkedin?: string | null;
  github?: string | null;
  portfolio?: string | null;
}

interface SubProject {
  name: string;
  description: string;
  technologies: string[];
  achievements: string[];
}

interface ExperienceItem {
  company: string;
  jobTitle: string;
  startDate: string;
  endDate?: string | null;
  current: boolean;
  description: string;
  responsibilities: string[];
  projects: SubProject[];
}

interface ProjectItem {
  name: string;
  description: string;
  technologies: string[];
}

interface EducationItem {
  degree: string;
  institution: string;
  year: string | number;
}

interface AchievementItem {
  title: string;
}

interface JobPreferencesData {
  jobTitles: string[];
  locations: string[];
  remotePreference: string | null;
  minimumSalary: string | number | null;
  employmentTypes: string[];
}

interface AdditionalInfoData {
  yearsOfExperience: string | number | null;
  totalProjects: string | null;
}

export default function ProfilePage() {
  const { user, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzingFilename, setAnalyzingFilename] = useState("");
  const [analysisSeconds, setAnalysisSeconds] = useState(0);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Form State ──────────────────────────────────────────────
  const [personal, setPersonal] = useState<PersonalData>({
    fullName: "",
    email: "",
    phone: "",
    location: { address: "", city: "", postalCode: "", country: "" },
    linkedin: "",
    github: "",
    portfolio: "",
  });
  const [summary, setSummary] = useState("");
  const [skills, setSkills] = useState<Record<string, string[]>>({
    backend: [],
    frontend: [],
    languages: [],
    databases: [],
    ui: [],
    tools: [],
    architecture: [],
  });
  const [newSkillInputs, setNewSkillInputs] = useState<Record<string, string>>({});
  const [newCategoryName, setNewCategoryName] = useState("");

  const [experience, setExperience] = useState<ExperienceItem[]>([]);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [education, setEducation] = useState<EducationItem[]>([]);
  const [achievements, setAchievements] = useState<AchievementItem[]>([]);
  const [jobPreferences, setJobPreferences] = useState<JobPreferencesData>({
    jobTitles: [],
    locations: [],
    remotePreference: "any",
    minimumSalary: "",
    employmentTypes: ["full-time"],
  });
  const [additionalInfo, setAdditionalInfo] = useState<AdditionalInfoData>({
    yearsOfExperience: "",
    totalProjects: "",
  });
  const [selectedTemplate, setSelectedTemplate] = useState<string>("default");
  const [screeningTrigger, setScreeningTrigger] = useState(0);

  // Collapsible section toggles
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    personal: true,
    summary: true,
    skills: true,
    experience: true,
    projects: true,
    education: true,
    achievements: true,
    preferences: true,
  });

  const toggleSection = (s: string) => setExpanded((prev) => ({ ...prev, [s]: !prev[s] }));

const sanitizeStr = (val: unknown): string => {
  if (typeof val !== "string") return "";
  const s = val.trim();
  if (["null", "none", "nil", "undefined", "n/a", "na"].includes(s.toLowerCase())) return "";
  return s;
};

  // ── Populate form from DB profile ──────────────────────────
  const populateForm = (p: Record<string, unknown> | null) => {
    if (!p) return;
    setProfile(p);

    const pers = (p.personal as Record<string, unknown>) ?? {};
    const loc = pers.location;
    const structuredLoc: LocationData =
      typeof loc === "object" && loc !== null
        ? {
            address: sanitizeStr((loc as LocationData).address),
            city: sanitizeStr((loc as LocationData).city),
            postalCode: sanitizeStr((loc as LocationData).postalCode),
            country: sanitizeStr((loc as LocationData).country),
          }
        : { address: "", city: typeof loc === "string" ? sanitizeStr(loc) : "", postalCode: "", country: "" };

    setPersonal({
      fullName: sanitizeStr(pers.fullName || pers.full_name),
      email: sanitizeStr(pers.email),
      phone: sanitizeStr(pers.phone),
      location: structuredLoc,
      linkedin: sanitizeStr(pers.linkedin),
      github: sanitizeStr(pers.github),
      portfolio: sanitizeStr(pers.portfolio),
    });

    setSummary(sanitizeStr(p.summary));

    // Skills: handle both categorized dictionary and flat array
    const rawSkills = p.skills;
    if (rawSkills && typeof rawSkills === "object" && !Array.isArray(rawSkills)) {
      const cleanedSkillsMap: Record<string, string[]> = {};
      for (const [k, v] of Object.entries(rawSkills as Record<string, unknown>)) {
        if (Array.isArray(v)) {
          cleanedSkillsMap[k] = v.map(sanitizeStr).filter((s) => s.length > 0);
        }
      }
      setSkills(cleanedSkillsMap);
    } else if (Array.isArray(rawSkills)) {
      setSkills({ general: rawSkills.map(sanitizeStr).filter((s) => s.length > 0) });
    }

    // Experience
    const rawExp = (p.experience as Array<Record<string, unknown>>) || [];
    setExperience(
      rawExp
        .map((e) => {
          const comp = sanitizeStr(e.company);
          const title = sanitizeStr(e.jobTitle || e.title);
          const start = sanitizeStr(e.startDate || e.start_date);
          const endRaw = sanitizeStr(e.endDate || e.end_date);
          const isCurr = Boolean(e.current ?? e.is_current);
          const desc = sanitizeStr(e.description);

          const rawResp = (e.responsibilities as unknown[]) || [];
          const cleanResp = rawResp.map(sanitizeStr).filter((r) => r.length > 0);

          const rawSubProjects = (e.projects as Array<Record<string, unknown>>) || [];
          const cleanSubProjects = rawSubProjects
            .map((sub) => ({
              name: sanitizeStr(sub.name),
              description: sanitizeStr(sub.description),
              technologies: ((sub.technologies as unknown[]) || []).map(sanitizeStr).filter((t) => t.length > 0),
              achievements: ((sub.achievements as unknown[]) || []).map(sanitizeStr).filter((a) => a.length > 0),
            }))
            .filter((sub) => sub.name.length > 0);

          return {
            company: comp,
            jobTitle: title,
            startDate: start,
            endDate: isCurr ? "Present" : endRaw || null,
            current: isCurr,
            description: desc,
            responsibilities: cleanResp,
            projects: cleanSubProjects,
          };
        })
        .filter((e) => e.company.length > 0 || e.jobTitle.length > 0)
    );

    // Projects
    const rawProj = (p.projects as Array<Record<string, unknown>>) || [];
    setProjects(
      rawProj
        .map((pr) => ({
          name: sanitizeStr(pr.name),
          description: sanitizeStr(pr.description),
          technologies: ((pr.technologies as unknown[]) || []).map(sanitizeStr).filter((t) => t.length > 0),
        }))
        .filter((pr) => pr.name.length > 0)
    );

    // Education
    const rawEdu = (p.education as Array<Record<string, unknown>>) || [];
    setEducation(
      rawEdu
        .map((ed) => ({
          degree: sanitizeStr(ed.degree),
          institution: sanitizeStr(ed.institution),
          year: sanitizeStr(ed.year || ed.graduation_year),
        }))
        .filter((ed) => ed.degree.length > 0 || ed.institution.length > 0)
    );

    // Achievements
    const rawAch = (p.achievements as Array<Record<string, unknown> | string>) || [];
    setAchievements(
      rawAch
        .map((a) => (typeof a === "string" ? { title: sanitizeStr(a) } : { title: sanitizeStr(a.title) }))
        .filter((a) => a.title.length > 0)
    );

    // Job Preferences
    const rawPref = (p.jobPreferences as Record<string, unknown>) || (p.job_preferences as Record<string, unknown>) || {};
    setJobPreferences({
      jobTitles: (rawPref.jobTitles as string[]) || (rawPref.titles as string[]) || [],
      locations: (rawPref.locations as string[]) || [],
      remotePreference: (rawPref.remotePreference as string) || (rawPref.remote_preference as string) || "any",
      minimumSalary: (rawPref.minimumSalary as number | string) || (rawPref.salary_min as number | string) || "",
      employmentTypes: (rawPref.employmentTypes as string[]) || (rawPref.types as string[]) || ["full-time"],
    });

    // Additional Info
    const rawAdd = (p.additionalInformation as Record<string, unknown>) || {};
    setAdditionalInfo({
      yearsOfExperience: (rawAdd.yearsOfExperience as number | string) ?? "",
      totalProjects: (rawAdd.totalProjects as string) ?? "",
    });

    // Selected Resume Template
    setSelectedTemplate(String(p.selected_template || p.selectedTemplate || "default"));
  };

  const stopAnalysis = () => {
    setIsAnalyzing(false);
    setUploading(false);
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  };

  const startAnalysisTracking = (filename?: string) => {
    stopAnalysis();
    setIsAnalyzing(true);
    setUploading(true);
    setAnalyzingFilename(filename || "resume.pdf");
    setAnalysisSeconds(0);
    setUploadError("");
    setUploadMsg("AI is parsing your resume: extracting all work experiences, projects, skills & education... (takes ~30-60s)");

    timerIntervalRef.current = setInterval(() => {
      setAnalysisSeconds((prev) => prev + 1);
    }, 1000);

    let attempts = 0;
    const maxAttempts = 60; // 60 * 2s = 120 seconds max
    pollIntervalRef.current = setInterval(async () => {
      attempts++;
      try {
        const updated = await profileApi.get();
        const p = updated?.profile;
        if (p) {
          // Auto-fill details continuously as each step parses data
          if (
            p.personal?.fullName ||
            (Array.isArray(p.experience) && p.experience.length > 0) ||
            (p.skills && Object.keys(p.skills).length > 0)
          ) {
            populateForm(p);
          }

          if (p.analysis_error) {
            stopAnalysis();
            setUploadError("Analysis error: " + String(p.analysis_error));
            void load();
            return;
          }

          // When backend finishes, stop analysis and finalize
          if (!p.is_analyzing) {
            stopAnalysis();
            populateForm(p);
            setUploadMsg("✓ Resume parsed successfully! Extracted all work experiences, skills, and projects.");
            setScreeningTrigger((prev) => prev + 1);
            return;
          }
        }
        if (attempts >= maxAttempts) {
          stopAnalysis();
          if (p) populateForm(p);
          setUploadMsg("Analysis complete. Review your extracted profile below.");
          setScreeningTrigger((prev) => prev + 1);
        }
      } catch {
        // Keep polling
      }
    }, 2000);
  };

  const load = async () => {
    try {
      const [p, q] = await Promise.all([profileApi.get(), profileApi.getQuestions()]);
      if (p?.profile) {
        populateForm(p.profile);
        if (p.profile.is_analyzing) {
          startAnalysisTracking(p.profile.resume_filename as string);
        } else if (isAnalyzing) {
          stopAnalysis();
        }
      }
      if (q?.questions) setQuestions(q.questions as Question[]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!msg.includes("Invalid or expired token") && !msg.includes("401")) {
        console.error("Failed to load profile data:", err);
      }
    }
  };

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, []);

  useEffect(() => {
    if (!authLoading && user) {
      void load();
    }
  }, [authLoading, user?.id]);

  // ── Upload Resume & Dropzone Handlers ────────────────────────
  const processResumeFile = async (file: File) => {
    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith(".pdf") && !fileName.endsWith(".docx")) {
      setUploadError("Please upload a PDF or DOCX document (.pdf, .docx)");
      setUploadMsg("");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File size exceeds 10MB limit");
      setUploadMsg("");
      return;
    }

    setUploadError("");

    // Immediately clear old form state so previous resume data is deleted from UI
    setPersonal({
      fullName: "",
      email: "",
      phone: "",
      location: { address: "", city: "", postalCode: "", country: "" },
      linkedin: "",
      github: "",
      portfolio: "",
    });
    setSummary("");
    setSkills({
      backend: [],
      frontend: [],
      languages: [],
      databases: [],
      ui: [],
      tools: [],
      architecture: [],
    });
    setExperience([]);
    setProjects([]);
    setEducation([]);
    setAchievements([]);
    setJobPreferences({
      jobTitles: [],
      locations: [],
      remotePreference: "any",
      minimumSalary: "",
      employmentTypes: ["full-time"],
    });
    setAdditionalInfo({
      yearsOfExperience: "",
      totalProjects: "",
    });

    startAnalysisTracking(file.name);

    try {
      await profileApi.uploadResume(file);
    } catch (err: unknown) {
      stopAnalysis();
      setUploadError(err instanceof Error ? err.message : "Upload failed");
      void load();
    }
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await processResumeFile(file);
    }
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!uploading) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (uploading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) {
      await processResumeFile(file);
    }
  };

  // ── Save Full Profile ───────────────────────────────────────
  const handleSaveProfile = async () => {
    setSaving(true);
    setSaveSuccess(false);
    try {
      const payload = {
        personal: {
          fullName: personal.fullName,
          full_name: personal.fullName,
          email: personal.email,
          phone: personal.phone,
          location: personal.location,
          linkedin: personal.linkedin,
          github: personal.github,
          portfolio: personal.portfolio,
        },
        summary,
        skills,
        experience,
        projects,
        education,
        achievements,
        jobPreferences,
        job_preferences: jobPreferences,
        additionalInformation: additionalInfo,
        selected_template: selectedTemplate,
      };

      const res = await profileApi.patch(payload);
      populateForm(res.profile);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3500);
    } catch (err) {
      console.error("Save error:", err);
    } finally {
      setSaving(false);
    }
  };

  const handleSelectTemplate = async (templateId: string) => {
    setSelectedTemplate(templateId);
    try {
      await templatesApi.select(templateId);
    } catch (err) {
      console.error("Failed to select template:", err);
    }
  };

  // ── Questions ───────────────────────────────────────────────
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

  // ── Skill Tag Helpers ───────────────────────────────────────
  const addSkill = (category: string) => {
    const val = (newSkillInputs[category] || "").trim();
    if (!val) return;
    setSkills((prev) => ({
      ...prev,
      [category]: [...(prev[category] || []), val],
    }));
    setNewSkillInputs((prev) => ({ ...prev, [category]: "" }));
  };

  const removeSkill = (category: string, index: number) => {
    setSkills((prev) => ({
      ...prev,
      [category]: prev[category].filter((_, i) => i !== index),
    }));
  };

  const addCategory = () => {
    const cat = newCategoryName.trim().toLowerCase();
    if (!cat || skills[cat]) return;
    setSkills((prev) => ({ ...prev, [cat]: [] }));
    setNewCategoryName("");
  };

  const completion = (profile?.completion_score as number) ?? 0;

  return (
    <div className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-5xl mx-auto pb-24">
      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Profile</h1>
          <p className="text-slate-400 text-sm mt-1">
            Prefilled with AI from your resume. Edit and customize every detail for tailored applications.
          </p>
        </div>
        <button
          onClick={handleSaveProfile}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm shadow-lg shadow-indigo-600/30 hover:shadow-indigo-600/50 transition-all disabled:opacity-50 cursor-pointer self-start sm:self-auto"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving…" : "Save Profile"}
        </button>
      </div>

      {/* Save Success Toast */}
      <AnimatePresence>
        {saveSuccess && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mb-6 p-4 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2 shadow-lg"
          >
            <CheckCircle className="w-5 h-5 text-emerald-400" />
            Profile changes saved successfully!
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Completeness & Resume Dropzone ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-8">
        {/* Completeness bar */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-indigo-400" />
                <span className="text-sm font-semibold text-white">Profile Completeness</span>
              </div>
              <span className={`text-sm font-black ${isAnalyzing ? "text-indigo-400" : completion >= 75 ? "score-high" : completion >= 50 ? "score-medium" : "score-low"}`}>
                {isAnalyzing ? (
                  <span className="flex items-center gap-1.5 text-xs text-indigo-400 font-semibold bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/30">
                    <Loader2 className="w-3 h-3 animate-spin" /> AI Analyzing...
                  </span>
                ) : (
                  `${completion}%`
                )}
              </span>
            </div>
            <div className="h-2 bg-white/10 rounded-full overflow-hidden mt-3 relative">
              {isAnalyzing ? (
                <motion.div
                  initial={{ x: "-100%" }}
                  animate={{ x: "100%" }}
                  transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                  className="h-full w-1/2 rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500"
                />
              ) : (
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${completion}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                  className="h-full rounded-full"
                  style={{ background: `linear-gradient(90deg, rgb(var(--theme-c1)), rgb(var(--theme-c2)))` }}
                />
              )}
            </div>
            <p className="text-xs text-slate-400 mt-3 leading-relaxed">
              {isAnalyzing
                ? "AI is extracting all work experiences, projects, and skills from your resume into structured ATS fields."
                : "A comprehensive profile dramatically improves AI matching accuracy and resume tailoring for your job applications."}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-4 pt-4 border-t border-white/5 text-xs">
            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white/[0.02]">
              <span className="text-slate-500">Skills</span>
              <span className={`font-semibold ${isAnalyzing ? "text-indigo-400 animate-pulse text-[11px]" : "text-white"}`}>
                {isAnalyzing ? "Extracting..." : `${Object.values(skills).flat().length} tags`}
              </span>
            </div>
            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white/[0.02]">
              <span className="text-slate-500">Experience</span>
              <span className={`font-semibold ${isAnalyzing ? "text-indigo-400 animate-pulse text-[11px]" : "text-white"}`}>
                {isAnalyzing ? "Extracting..." : `${experience.length} roles`}
              </span>
            </div>
            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white/[0.02]">
              <span className="text-slate-500">Projects</span>
              <span className={`font-semibold ${isAnalyzing ? "text-indigo-400 animate-pulse text-[11px]" : "text-white"}`}>
                {isAnalyzing ? "Extracting..." : `${projects.length} listed`}
              </span>
            </div>
            <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white/[0.02]">
              <span className="text-slate-500">Education</span>
              <span className={`font-semibold ${isAnalyzing ? "text-indigo-400 animate-pulse text-[11px]" : "text-white"}`}>
                {isAnalyzing ? "Extracting..." : `${education.length} degrees`}
              </span>
            </div>
          </div>
        </motion.div>

        {/* Resume Dropzone */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass rounded-2xl p-5 flex flex-col justify-between"
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileUp className="w-4 h-4 text-indigo-400" />
              <h2 className="font-bold text-sm text-white">Resume Document</h2>
            </div>
            <span className="text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              AI Dropzone
            </span>
          </div>

          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={handleFileInputChange}
          />

          <div
            onClick={() => !isAnalyzing && !uploading && fileRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`relative rounded-xl border-2 border-dashed p-5 transition-all duration-200 cursor-pointer flex flex-col items-center justify-center text-center ${
              isDragging
                ? "border-indigo-400 bg-indigo-500/15 shadow-[0_0_25px_rgba(99,102,241,0.25)] scale-[1.01]"
                : "border-white/15 bg-white/[0.02] hover:bg-white/[0.05] hover:border-indigo-400/40"
            } ${isAnalyzing || uploading ? "opacity-90 pointer-events-none" : ""}`}
          >
            {isAnalyzing || uploading ? (
              <div className="py-2.5 flex flex-col items-center gap-2.5">
                <div className="relative">
                  <div className="w-12 h-12 rounded-2xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center animate-pulse">
                    <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
                  </div>
                  <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-emerald-400 animate-ping pointer-events-none" />
                </div>
                <div>
                  <p className="text-xs font-bold text-white flex items-center justify-center gap-1.5">
                    Analyzing Resume with AI…
                  </p>
                  <p className="text-[11px] text-indigo-300 font-mono mt-0.5">
                    {analysisSeconds}s elapsed · Extracting roles, skills & education
                  </p>
                </div>
              </div>
            ) : (
              <div className="py-1 flex flex-col items-center gap-2">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                    isDragging
                      ? "bg-indigo-500 text-white scale-110 shadow-lg shadow-indigo-500/40"
                      : "bg-white/5 border border-white/10 text-indigo-400"
                  }`}
                >
                  {isDragging ? <Sparkles className="w-5 h-5 animate-pulse" /> : <Upload className="w-5 h-5" />}
                </div>

                <div>
                  <p className="text-xs font-semibold text-white">
                    {isDragging ? (
                      <span className="text-indigo-400 font-bold">Drop PDF here to upload</span>
                    ) : (
                      <>
                        <span className="text-indigo-400 underline decoration-indigo-400/40 underline-offset-2 hover:decoration-indigo-400">
                          Click to browse
                        </span>{" "}
                        or drag & drop
                      </>
                    )}
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    PDF or DOCX up to 10MB · Automatically pre-fills your profile form
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Current file status or notifications */}
          <div className="mt-3 space-y-2">
            {Boolean(profile?.resume_filename || analyzingFilename) && (
              <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs">
                <div className="flex items-center gap-2 truncate">
                  <FileText className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                  <span className="text-slate-200 truncate font-medium max-w-[200px] sm:max-w-[260px]">
                    {String(analyzingFilename || profile?.resume_filename)}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0 ${
                    isAnalyzing
                      ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 animate-pulse"
                      : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  }`}>
                    {isAnalyzing ? "Analyzing" : "Active"}
                  </span>
                </div>
                {!isAnalyzing && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      fileRef.current?.click();
                    }}
                    className="text-[11px] text-slate-400 hover:text-indigo-300 transition-colors shrink-0 ml-2 cursor-pointer font-medium"
                  >
                    Replace
                  </button>
                )}
              </div>
            )}

            {uploadMsg && (
              <p className="text-xs text-emerald-400 flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                <CheckCircle className="w-3.5 h-3.5 shrink-0" /> {uploadMsg}
              </p>
            )}

            {uploadError && (
              <p className="text-xs text-rose-400 flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-500/10 border border-rose-500/20">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {uploadError}
              </p>
            )}
          </div>
        </motion.div>
      </div>

      {/* ── Active Live AI Analysis Progress Card ── */}
      {isAnalyzing && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass rounded-3xl p-6 sm:p-7 mb-8 border-2 border-indigo-500/40 bg-gradient-to-r from-indigo-950/60 via-purple-950/40 to-slate-900/80 shadow-[0_0_40px_rgba(99,102,241,0.25)] relative overflow-hidden backdrop-blur-xl"
        >
          <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5 pb-5 border-b border-white/10 relative z-10">
            <div className="flex items-center gap-3.5">
              <div className="relative">
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center">
                  <Sparkles className="w-6 h-6 text-indigo-400 animate-pulse" />
                </div>
                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-emerald-400 border-2 border-slate-950 animate-ping" />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Local AI Model Parsing
                  </span>
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-mono font-semibold border border-indigo-500/30">
                    {analysisSeconds}s elapsed
                  </span>
                </div>
                <h3 className="text-lg sm:text-xl font-black text-white">
                  Extracting Profile from &ldquo;{analyzingFilename || String(profile?.resume_filename || "Uploaded Resume")}&rdquo;
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  The local AI engine is reading all sections. Work experience, skills, and ATS preview will update below automatically.
                </p>
              </div>
            </div>
            <div className="text-right hidden sm:block">
              <span className="text-[11px] text-slate-400">Typical duration</span>
              <p className="text-sm font-bold text-indigo-300 font-mono">~20 – 35 seconds</p>
            </div>
          </div>

          {/* 4-Step Live Extraction Tracker */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 relative z-10">
            <div className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 transition-all ${
              analysisSeconds >= 2 ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-indigo-500/15 border-indigo-500/30 text-indigo-200"
            }`}>
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              <div>
                <p className="font-semibold text-white">1. Text & Layout</p>
                <p className="text-[10px] text-slate-400">Document parsed</p>
              </div>
            </div>

            <div className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 transition-all ${
              analysisSeconds >= 10 ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : "bg-indigo-500/20 border-indigo-500/40 text-indigo-200 animate-pulse"
            }`}>
              {analysisSeconds >= 10 ? <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" /> : <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />}
              <div>
                <p className="font-semibold text-white">2. Work History</p>
                <p className="text-[10px] text-slate-400">Roles & achievements</p>
              </div>
            </div>

            <div className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 transition-all ${
              analysisSeconds >= 18 ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300" : analysisSeconds >= 10 ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-200 animate-pulse" : "bg-white/[0.02] border-white/10 text-slate-500"
            }`}>
              {analysisSeconds >= 18 ? <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" /> : analysisSeconds >= 10 ? <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" /> : <span className="w-4 h-4 rounded-full border border-slate-600 inline-block shrink-0" />}
              <div>
                <p className="font-semibold text-white">3. Tech Stack</p>
                <p className="text-[10px] text-slate-400">Skills & frameworks</p>
              </div>
            </div>

            <div className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 transition-all ${
              analysisSeconds >= 24 ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-200 animate-pulse" : "bg-white/[0.02] border-white/10 text-slate-500"
            }`}>
              {analysisSeconds >= 24 ? <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" /> : <span className="w-4 h-4 rounded-full border border-slate-600 inline-block shrink-0" />}
              <div>
                <p className="font-semibold text-white">4. Finalizing</p>
                <p className="text-[10px] text-slate-400">Recruiter Q&A & ATS</p>
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* ── Resume Template Selector & Live Preview ── */}
      <ResumeTemplateSelector
        personal={personal}
        summary={summary}
        skills={skills}
        experience={experience}
        projects={projects}
        education={education}
        achievements={achievements}
        currentTemplate={selectedTemplate}
        isAnalyzing={isAnalyzing}
        onSelectTemplate={handleSelectTemplate}
      />

      {/* ── AI Target Profile Selection & Recruiter Screening Q&A ── */}
      <ResumeScreeningQA key={screeningTrigger} onProfileUpdated={load} />

      {/* ── EDITABLE FORM SECTIONS ── */}
      <div className="space-y-6">

        {/* 1. Personal & Contact Information */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("personal")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-indigo-500/15 text-indigo-400"><User className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Personal & Contact Details</h3>
                <p className="text-xs text-slate-500">Name, contact numbers, portfolio, and location</p>
              </div>
            </div>
            {expanded.personal ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.personal && (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Full Name</label>
                  <input
                    type="text"
                    value={personal.fullName || ""}
                    onChange={(e) => setPersonal({ ...personal, fullName: e.target.value })}
                    placeholder="Full name"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Email</label>
                  <input
                    type="email"
                    value={personal.email || ""}
                    onChange={(e) => setPersonal({ ...personal, email: e.target.value })}
                    placeholder="Email address"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Phone</label>
                  <input
                    type="text"
                    value={personal.phone || ""}
                    onChange={(e) => setPersonal({ ...personal, phone: e.target.value })}
                    placeholder="Phone number"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Nested Location */}
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                <div className="flex items-center gap-2 mb-3 text-xs font-semibold text-slate-300">
                  <MapPin className="w-3.5 h-3.5 text-indigo-400" /> Location Details
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">Address / Area</label>
                    <input
                      type="text"
                      value={typeof personal.location === "object" ? personal.location?.address || "" : ""}
                      onChange={(e) => {
                        const cur = typeof personal.location === "object" ? personal.location : {};
                        setPersonal({ ...personal, location: { ...cur, address: e.target.value } });
                      }}
                      placeholder="Street address or area"
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">City</label>
                    <input
                      type="text"
                      value={typeof personal.location === "object" ? personal.location?.city || "" : typeof personal.location === "string" ? personal.location : ""}
                      onChange={(e) => {
                        const cur = typeof personal.location === "object" ? personal.location : {};
                        setPersonal({ ...personal, location: { ...cur, city: e.target.value } });
                      }}
                      placeholder="City"
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">Postal Code</label>
                    <input
                      type="text"
                      value={typeof personal.location === "object" ? personal.location?.postalCode || "" : ""}
                      onChange={(e) => {
                        const cur = typeof personal.location === "object" ? personal.location : {};
                        setPersonal({ ...personal, location: { ...cur, postalCode: e.target.value } });
                      }}
                      placeholder="Postal code"
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">Country</label>
                    <input
                      type="text"
                      value={typeof personal.location === "object" ? personal.location?.country || "" : ""}
                      onChange={(e) => {
                        const cur = typeof personal.location === "object" ? personal.location : {};
                        setPersonal({ ...personal, location: { ...cur, country: e.target.value } });
                      }}
                      placeholder="Country"
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* Online Links */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Portfolio / Website</label>
                  <input
                    type="text"
                    value={personal.portfolio || ""}
                    onChange={(e) => setPersonal({ ...personal, portfolio: e.target.value })}
                    placeholder="Portfolio or website URL"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">GitHub URL</label>
                  <input
                    type="text"
                    value={personal.github || ""}
                    onChange={(e) => setPersonal({ ...personal, github: e.target.value })}
                    placeholder="GitHub profile URL"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">LinkedIn URL</label>
                  <input
                    type="text"
                    value={personal.linkedin || ""}
                    onChange={(e) => setPersonal({ ...personal, linkedin: e.target.value })}
                    placeholder="LinkedIn profile URL"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 2. Professional Summary */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("summary")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-purple-500/15 text-purple-400"><Sparkles className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Professional Summary</h3>
                <p className="text-xs text-slate-500">AI-generated pitch highlighting your core value</p>
              </div>
            </div>
            {expanded.summary ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.summary && (
            <div className="p-5">
              <textarea
                rows={4}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder="Write or review your professional summary…"
                className="w-full bg-white/5 border border-white/10 rounded-xl p-3 text-sm text-white leading-relaxed focus:outline-none focus:border-indigo-500"
              />
              <p className="text-[11px] text-slate-500 mt-2 text-right">{summary.length} characters</p>
            </div>
          )}
        </div>

        {/* 3. Categorized Skills */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("skills")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-emerald-500/15 text-emerald-400"><Award className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Categorized Technical Skills</h3>
                <p className="text-xs text-slate-500">Backend, Frontend, Languages, Databases, Tools, Architecture</p>
              </div>
            </div>
            {expanded.skills ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.skills && (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Object.entries(skills).map(([cat, list]) => (
                  <div key={cat} className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-indigo-300 uppercase tracking-wider">{cat}</span>
                      <span className="text-[10px] text-slate-500">{list.length} skills</span>
                    </div>

                    <div className="flex flex-wrap gap-1.5 mb-2.5 min-h-[30px]">
                      {list.map((item, idx) => (
                        <span
                          key={item + idx}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-indigo-500/15 text-indigo-200 border border-indigo-500/30"
                        >
                          {item}
                          <button
                            type="button"
                            onClick={() => removeSkill(cat, idx)}
                            className="hover:text-red-400 text-slate-400"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))}
                    </div>

                    {/* Inline add skill */}
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newSkillInputs[cat] || ""}
                        onChange={(e) => setNewSkillInputs({ ...newSkillInputs, [cat]: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            addSkill(cat);
                          }
                        }}
                        placeholder={`Add ${cat} skill + press Enter`}
                        className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500"
                      />
                      <button
                        type="button"
                        onClick={() => addSkill(cat)}
                        className="p-1 px-2.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600 text-indigo-200 text-xs font-semibold cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Add Custom Category */}
              <div className="flex items-center gap-3 pt-2">
                <input
                  type="text"
                  value={newCategoryName}
                  onChange={(e) => setNewCategoryName(e.target.value)}
                  placeholder="New skill category name…"
                  className="bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500"
                />
                <button
                  type="button"
                  onClick={addCategory}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Category
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 4. Work Experience */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("experience")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-yellow-500/15 text-yellow-400"><Briefcase className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Work Experience ({experience.length})</h3>
                <p className="text-xs text-slate-500">Roles, responsibilities, and internal projects</p>
              </div>
            </div>
            {expanded.experience ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.experience && (
            <div className="p-5 space-y-6">
              {experience.map((exp, expIdx) => (
                <div key={expIdx} className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 flex-1">
                      <div>
                        <label className="text-[11px] text-slate-500 mb-1 block">Company</label>
                        <input
                          type="text"
                          value={exp.company}
                          onChange={(e) => {
                            const updated = [...experience];
                            updated[expIdx].company = e.target.value;
                            setExperience(updated);
                          }}
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white font-semibold focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-slate-500 mb-1 block">Job Title</label>
                        <input
                          type="text"
                          value={exp.jobTitle}
                          onChange={(e) => {
                            const updated = [...experience];
                            updated[expIdx].jobTitle = e.target.value;
                            setExperience(updated);
                          }}
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setExperience(experience.filter((_, i) => i !== expIdx))}
                      className="p-1.5 text-slate-500 hover:text-red-400 rounded-lg hover:bg-white/5"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="text-[11px] text-slate-500 mb-1 block">Start Date</label>
                      <input
                        type="text"
                        value={exp.startDate}
                        onChange={(e) => {
                          const updated = [...experience];
                          updated[expIdx].startDate = e.target.value;
                          setExperience(updated);
                        }}
                        placeholder="YYYY-MM"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[11px] text-slate-500 mb-1 block">End Date</label>
                      <input
                        type="text"
                        value={exp.endDate || ""}
                        disabled={exp.current}
                        onChange={(e) => {
                          const updated = [...experience];
                          updated[expIdx].endDate = e.target.value;
                          setExperience(updated);
                        }}
                        placeholder={exp.current ? "Present" : "YYYY-MM"}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white disabled:opacity-50 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div className="flex items-center pt-5">
                      <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                        <input
                          type="checkbox"
                          checked={exp.current}
                          onChange={(e) => {
                            const updated = [...experience];
                            updated[expIdx].current = e.target.checked;
                            if (e.target.checked) updated[expIdx].endDate = null;
                            setExperience(updated);
                          }}
                          className="rounded border-white/20 bg-white/5 text-indigo-600 focus:ring-0"
                        />
                        Currently working here
                      </label>
                    </div>
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">Company Description</label>
                    <textarea
                      rows={2}
                      value={exp.description}
                      onChange={(e) => {
                        const updated = [...experience];
                        updated[expIdx].description = e.target.value;
                        setExperience(updated);
                      }}
                      className="w-full bg-white/5 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  {/* Responsibilities */}
                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">Key Responsibilities (One per line)</label>
                    <textarea
                      rows={3}
                      value={(exp.responsibilities || []).join("\n")}
                      onChange={(e) => {
                        const updated = [...experience];
                        updated[expIdx].responsibilities = e.target.value.split("\n").filter((l) => l.trim());
                        setExperience(updated);
                      }}
                      placeholder="Key responsibilities and achievements (one per line)…"
                      className="w-full bg-white/5 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  {/* Sub-projects inside company */}
                  {(exp.projects || []).length > 0 && (
                    <div className="pt-2 border-t border-white/5 space-y-3">
                      <p className="text-[11px] font-semibold text-slate-400">Featured Projects at {exp.company || "Company"}:</p>
                      {exp.projects.map((sub, sIdx) => (
                        <div key={sIdx} className="p-3 rounded-lg bg-black/20 border border-white/5 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-white">{sub.name || "Project"}</span>
                            <button
                              type="button"
                              onClick={() => {
                                const updated = [...experience];
                                updated[expIdx].projects = updated[expIdx].projects.filter((_, i) => i !== sIdx);
                                setExperience(updated);
                              }}
                              className="text-slate-500 hover:text-red-400 text-xs"
                            >
                              Remove
                            </button>
                          </div>
                          <p className="text-xs text-slate-400">{sub.description}</p>
                          <div className="flex flex-wrap gap-1">
                            {sub.technologies.map((t) => (
                              <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-white/5 text-slate-300">{t}</span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              <button
                type="button"
                onClick={() =>
                  setExperience([
                    ...experience,
                    {
                      company: "",
                      jobTitle: "",
                      startDate: "",
                      endDate: null,
                      current: false,
                      description: "",
                      responsibilities: [],
                      projects: [],
                    },
                  ])
                }
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" /> Add Experience
              </button>
            </div>
          )}
        </div>

        {/* 5. Independent Projects */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("projects")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-rose-500/15 text-rose-400"><Globe className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Independent / Client Projects ({projects.length})</h3>
                <p className="text-xs text-slate-500">Standalone web apps, open source, or freelance work</p>
              </div>
            </div>
            {expanded.projects ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.projects && (
            <div className="p-5 space-y-4">
              {projects.map((proj, pIdx) => (
                <div key={pIdx} className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 flex-1">
                      <div>
                        <label className="text-[11px] text-slate-500 mb-1 block">Project Name</label>
                        <input
                          type="text"
                          value={proj.name}
                          onChange={(e) => {
                            const updated = [...projects];
                            updated[pIdx].name = e.target.value;
                            setProjects(updated);
                          }}
                          placeholder="Project name"
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white font-semibold focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-slate-500 mb-1 block">Technologies (comma separated)</label>
                        <input
                          type="text"
                          value={proj.technologies.join(", ")}
                          onChange={(e) => {
                            const updated = [...projects];
                            updated[pIdx].technologies = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                            setProjects(updated);
                          }}
                          placeholder="Technologies used (comma separated)"
                          className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setProjects(projects.filter((_, i) => i !== pIdx))}
                      className="p-1.5 text-slate-500 hover:text-red-400 rounded-lg hover:bg-white/5"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-500 mb-1 block">Description</label>
                    <textarea
                      rows={2}
                      value={proj.description}
                      onChange={(e) => {
                        const updated = [...projects];
                        updated[pIdx].description = e.target.value;
                        setProjects(updated);
                      }}
                      className="w-full bg-white/5 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>
              ))}

              <button
                type="button"
                onClick={() => setProjects([...projects, { name: "", description: "", technologies: [] }])}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" /> Add Project
              </button>
            </div>
          )}
        </div>

        {/* 6. Education & Achievements */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("education")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-cyan-500/15 text-cyan-400"><GraduationCap className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Education & Achievements</h3>
                <p className="text-xs text-slate-500">Degrees, certifications, LeetCode / HackerRank badges</p>
              </div>
            </div>
            {expanded.education ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.education && (
            <div className="p-5 space-y-6">
              {/* Education List */}
              <div className="space-y-3">
                <p className="text-xs font-semibold text-slate-300">Degrees & Institutions</p>
                {education.map((edu, edIdx) => (
                  <div key={edIdx} className="grid grid-cols-1 sm:grid-cols-4 gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/5 items-center">
                    <div className="sm:col-span-2">
                      <input
                        type="text"
                        value={edu.degree}
                        onChange={(e) => {
                          const updated = [...education];
                          updated[edIdx].degree = e.target.value;
                          setEducation(updated);
                        }}
                        placeholder="Degree or qualification"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <input
                        type="text"
                        value={edu.institution}
                        onChange={(e) => {
                          const updated = [...education];
                          updated[edIdx].institution = e.target.value;
                          setEducation(updated);
                        }}
                        placeholder="Institution"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={String(edu.year || "")}
                        onChange={(e) => {
                          const updated = [...education];
                          updated[edIdx].year = e.target.value;
                          setEducation(updated);
                        }}
                        placeholder="Year"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      />
                      <button
                        type="button"
                        onClick={() => setEducation(education.filter((_, i) => i !== edIdx))}
                        className="p-1.5 text-slate-500 hover:text-red-400"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setEducation([...education, { degree: "", institution: "", year: "" }])}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Degree
                </button>
              </div>

              {/* Achievements */}
              <div className="pt-4 border-t border-white/5 space-y-3">
                <p className="text-xs font-semibold text-slate-300">Key Achievements & Badges</p>
                {achievements.map((ach, aIdx) => (
                  <div key={aIdx} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={ach.title}
                      onChange={(e) => {
                        const updated = [...achievements];
                        updated[aIdx].title = e.target.value;
                        setAchievements(updated);
                      }}
                      placeholder="Achievement, award, or certification"
                      className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => setAchievements(achievements.filter((_, i) => i !== aIdx))}
                      className="p-1.5 text-slate-500 hover:text-red-400"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setAchievements([...achievements, { title: "" }])}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Achievement
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 7. Job Preferences & Additional Info */}
        <div className="glass rounded-2xl overflow-hidden transition-all">
          <button
            onClick={() => toggleSection("preferences")}
            className="w-full flex items-center justify-between p-5 text-left border-b border-white/5 hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-blue-500/15 text-blue-400"><MapPin className="w-4 h-4" /></div>
              <div>
                <h3 className="font-bold text-sm text-white">Target Job Preferences & Stats</h3>
                <p className="text-xs text-slate-500">Target titles, locations, remote preference, years of experience</p>
              </div>
            </div>
            {expanded.preferences ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>

          {expanded.preferences && (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Target Job Titles (comma separated)</label>
                  <input
                    type="text"
                    value={jobPreferences.jobTitles.join(", ")}
                    onChange={(e) =>
                      setJobPreferences({
                        ...jobPreferences,
                        jobTitles: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                      })
                    }
                    placeholder="Target job titles (comma separated)"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Target Locations (comma separated)</label>
                  <input
                    type="text"
                    value={jobPreferences.locations.join(", ")}
                    onChange={(e) =>
                      setJobPreferences({
                        ...jobPreferences,
                        locations: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                      })
                    }
                    placeholder="Target locations (comma separated)"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Remote Preference</label>
                  <select
                    value={jobPreferences.remotePreference || "any"}
                    onChange={(e) => setJobPreferences({ ...jobPreferences, remotePreference: e.target.value })}
                    className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="any">Any / Open</option>
                    <option value="remote">Remote Only</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">On-site</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Years of Experience</label>
                  <input
                    type="number"
                    value={additionalInfo.yearsOfExperience ?? ""}
                    onChange={(e) => setAdditionalInfo({ ...additionalInfo, yearsOfExperience: e.target.value })}
                    placeholder="Years of experience"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">Total Projects Delivered</label>
                  <input
                    type="text"
                    value={additionalInfo.totalProjects || ""}
                    onChange={(e) => setAdditionalInfo({ ...additionalInfo, totalProjects: e.target.value })}
                    placeholder="Total projects delivered"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

      </div>

      {/* ── Bottom Save Action Bar ── */}
      <div className="mt-8 flex items-center justify-end gap-3 pt-6 border-t border-white/10">
        <button
          onClick={handleSaveProfile}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm shadow-lg shadow-indigo-600/40 hover:shadow-indigo-600/60 transition-all disabled:opacity-50 cursor-pointer"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving Changes…" : "Save All Profile Changes"}
        </button>
      </div>
    </div>
  );
}
