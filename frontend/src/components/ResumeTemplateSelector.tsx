"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, Check, Download, Sparkles, LayoutTemplate,
  Maximize2, Minimize2, CheckCircle2, ShieldCheck, ChevronRight,
  ExternalLink, Layers
} from "lucide-react";
import { templatesApi, ResumeTemplateItem } from "@/lib/api";

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
  achievements?: string[];
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

interface ResumeTemplateSelectorProps {
  personal: PersonalData;
  summary: string;
  skills: Record<string, string[]>;
  experience: ExperienceItem[];
  projects: ProjectItem[];
  education: EducationItem[];
  achievements: AchievementItem[];
  currentTemplate?: string;
  onSelectTemplate: (templateId: string) => Promise<void> | void;
}

export default function ResumeTemplateSelector({
  personal,
  summary,
  skills,
  experience,
  projects,
  education,
  achievements,
  currentTemplate = "default",
  onSelectTemplate,
}: ResumeTemplateSelectorProps) {
  const [templates, setTemplates] = useState<ResumeTemplateItem[]>([]);
  const [activeTemplateId, setActiveTemplateId] = useState<string>(currentTemplate);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [justSelected, setJustSelected] = useState<boolean>(false);
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);

  useEffect(() => {
    setActiveTemplateId(currentTemplate || "default");
  }, [currentTemplate]);

  useEffect(() => {
    async function fetchTemplates() {
      try {
        const res = await templatesApi.list();
        if (res?.templates) {
          setTemplates(res.templates);
        }
      } catch (err) {
        console.error("Failed to load templates:", err);
      }
    }
    fetchTemplates();
  }, []);

  const handleChoose = async (id: string) => {
    setActiveTemplateId(id);
    setSavingId(id);
    try {
      await onSelectTemplate(id);
      setJustSelected(true);
      setTimeout(() => setJustSelected(false), 2500);
    } catch (err) {
      console.error("Failed to select template:", err);
    } finally {
      setSavingId(null);
    }
  };

  const activeTemplate =
    templates.find((t) => t.id === activeTemplateId) ||
    templates[0] || {
      id: "default",
      name: "Default Clean ATS",
      tagline: "Custom layout matching your Google Doc with dual-side header & section dividers",
      badge: "Default",
      badge_color: "emerald",
      ats_score: 99,
      style: "Clean Dual-Header",
      primary_color: "#1e293b",
      secondary_color: "#0f172a",
      font_family: "Calibri / Arial",
      layout: "Dual-Side Header + Dividers",
      ideal_for: "Full Stack & Software Engineering Roles",
      features: [
        "Google Doc Exact Match",
        "Inline Contact Bar & Links",
        "Compact Skills Grid",
        "High ATS Readability (99%)",
      ],
    };

  // Helper strings for personal contacts
  const candidateName =
    personal.fullName || personal.full_name || "Alex Chen";
  const city =
    typeof personal.location === "object"
      ? [personal.location?.city, personal.location?.country]
          .filter(Boolean)
          .join(", ")
      : typeof personal.location === "string"
      ? personal.location
      : "Bengaluru, India";

  const contactList = [
    personal.email || "candidate@example.com",
    personal.phone || "+91 98765 43210",
    city,
    personal.linkedin ? "linkedin.com/in/" + personal.linkedin.replace(/https?:\/\/(www\.)?linkedin\.com\/in\/?/i, "") : null,
    personal.github ? "github.com/" + personal.github.replace(/https?:\/\/(www\.)?github\.com\/?/i, "") : null,
  ].filter(Boolean);

  // Template specific theme classes for the live resume paper preview
  const getTemplateTheme = (id: string) => {
    switch (id) {
      case "default":
        return {
          fontFamily: "Calibri, Arial, sans-serif",
          headerColor: "#1e293b",
          nameColor: "#0f172a",
          titleBorder: "1px solid #94a3b8",
          sectionHeader: "font-sans tracking-normal text-slate-900 uppercase text-xs font-black border-b border-slate-300 pb-1 mb-2",
          badgeBg: "bg-emerald-50 text-emerald-900 border-emerald-200",
          paperClass: "bg-white text-slate-800",
        };
      case "minimal_executive":
        return {
          fontFamily: "Georgia, serif",
          headerColor: "#0f766e",
          nameColor: "#0f766e",
          titleBorder: "1px solid #0f766e",
          sectionHeader: "font-serif tracking-wide text-teal-800 uppercase text-xs font-bold border-b border-teal-700/30 pb-1 mb-2",
          badgeBg: "bg-teal-50 text-teal-900 border-teal-200",
          paperClass: "bg-[#fafaf9] text-stone-800",
        };
      case "compact_developer":
        return {
          fontFamily: "ui-monospace, monospace",
          headerColor: "#7c3aed",
          nameColor: "#7c3aed",
          titleBorder: "1px solid #7c3aed",
          sectionHeader: "font-mono tracking-tight text-purple-700 uppercase text-xs font-black border-b border-purple-500/30 pb-1 mb-2 flex items-center gap-1.5",
          badgeBg: "bg-purple-50 text-purple-900 border-purple-200",
          paperClass: "bg-slate-50 text-slate-900 text-xs",
        };
      case "classic_ats":
        return {
          fontFamily: "Times New Roman, serif",
          headerColor: "#000000",
          nameColor: "#000000",
          titleBorder: "1px solid #000000",
          sectionHeader: "font-serif text-black uppercase text-xs font-bold border-b border-black pb-0.5 mb-2",
          badgeBg: "bg-gray-100 text-gray-900 border-gray-300",
          paperClass: "bg-white text-black",
        };
      case "modern_tech":
      default:
        return {
          fontFamily: "system-ui, -apple-system, sans-serif",
          headerColor: "#4f46e5",
          nameColor: "#0f172a",
          titleBorder: "2px solid #4f46e5",
          sectionHeader: "font-sans tracking-wider text-indigo-600 uppercase text-xs font-black border-b border-indigo-500/20 pb-1 mb-2.5",
          badgeBg: "bg-indigo-50 text-indigo-800 border-indigo-200",
          paperClass: "bg-white text-slate-800",
        };
    }
  };

  const theme = getTemplateTheme(activeTemplateId);

  return (
    <div className="glass rounded-3xl p-6 sm:p-8 mb-8 border border-white/10 shadow-2xl relative overflow-hidden">
      {/* Decorative gradient glow */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />

      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 relative z-10">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-400">
              <LayoutTemplate className="w-4 h-4" />
            </span>
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">
              Resume Templates & Styling
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold flex items-center gap-1">
              <ShieldCheck className="w-3 h-3 text-emerald-400" /> ATS Verified
            </span>
          </div>
          <h2 className="text-xl sm:text-2xl font-black text-white">
            Choose Your Resume Template
          </h2>
          <p className="text-slate-400 text-xs sm:text-sm mt-0.5">
            Select a tailored layout. Previews dynamically reflect your real profile data and can be downloaded as an editable Google Doc / Word file (.docx).
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-2">
          <a
            href={templatesApi.getDownloadUrl(activeTemplateId)}
            download
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white font-semibold text-xs border border-white/10 shadow hover:border-white/20 transition-all cursor-pointer"
            title="Download editable .docx for Google Docs / MS Word"
          >
            <Download className="w-3.5 h-3.5 text-indigo-400" />
            Download .docx
          </a>
        </div>
      </div>

      {/* Template Card Selection Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-8 relative z-10">
        {templates.map((tpl) => {
          const isSelected = tpl.id === activeTemplateId;
          const isSaving = savingId === tpl.id;

          return (
            <div
              key={tpl.id}
              onClick={() => handleChoose(tpl.id)}
              className={`group relative rounded-2xl p-4 cursor-pointer transition-all duration-200 border text-left flex flex-col justify-between ${
                isSelected
                  ? "bg-indigo-600/15 border-indigo-500 shadow-[0_0_20px_rgba(99,102,241,0.25)] ring-1 ring-indigo-500/50"
                  : "bg-white/[0.03] border-white/10 hover:border-white/25 hover:bg-white/[0.06]"
              }`}
            >
              <div>
                {/* Badge & ATS score */}
                <div className="flex items-center justify-between gap-1 mb-2.5">
                  <span
                    className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${
                      tpl.badge_color === "indigo"
                        ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                        : tpl.badge_color === "emerald"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : tpl.badge_color === "purple"
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : "bg-slate-500/20 text-slate-300 border border-slate-500/30"
                    }`}
                  >
                    {tpl.badge}
                  </span>

                  <span className="text-[11px] font-bold text-emerald-400 flex items-center gap-0.5">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    {tpl.ats_score}% ATS
                  </span>
                </div>

                {/* Title */}
                <h3 className="font-bold text-sm text-white group-hover:text-indigo-300 transition-colors">
                  {tpl.name}
                </h3>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                  {tpl.tagline}
                </p>

                {/* Meta details */}
                <div className="mt-3 pt-2.5 border-t border-white/5 space-y-1 text-[11px] text-slate-400">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Font:</span>
                    <span className="text-slate-300 font-medium truncate max-w-[120px]">
                      {tpl.font_family}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Layout:</span>
                    <span className="text-slate-300 font-medium truncate max-w-[120px]">
                      {tpl.layout}
                    </span>
                  </div>
                </div>
              </div>

              {/* Status indicator button */}
              <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between">
                <span className="text-[11px] font-semibold text-slate-400">
                  {isSelected ? (
                    <span className="text-indigo-400 flex items-center gap-1">
                      <Check className="w-3.5 h-3.5 text-indigo-400" /> Active Template
                    </span>
                  ) : (
                    <span className="group-hover:text-white transition-colors">
                      Click to Preview
                    </span>
                  )}
                </span>
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center transition-all ${
                    isSelected
                      ? "bg-indigo-500 text-white shadow"
                      : "bg-white/10 text-transparent group-hover:border group-hover:border-white/30"
                  }`}
                >
                  <Check className="w-3 h-3" />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected notification toast */}
      <AnimatePresence>
        {justSelected && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-4 p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2"
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              <strong>{activeTemplate.name}</strong> selected as your default resume template! Applications and downloads will use this formatting.
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── LIVE INTERACTIVE PREVIEW SHEET ── */}
      <div className="relative">
        {/* Preview Control Header */}
        <div className="flex items-center justify-between bg-slate-900/90 border border-white/10 rounded-t-2xl px-5 py-3 text-xs">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-bold text-white tracking-wide">
              Live Preview: {activeTemplate.name}
            </span>
            <span className="hidden sm:inline text-slate-400">
              — Renders with your actual details below
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsFullScreen(!isFullScreen)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white transition-colors cursor-pointer text-[11px]"
            >
              {isFullScreen ? (
                <>
                  <Minimize2 className="w-3.5 h-3.5" /> Compact View
                </>
              ) : (
                <>
                  <Maximize2 className="w-3.5 h-3.5" /> Full Size
                </>
              )}
            </button>
            <a
              href={templatesApi.getDownloadUrl(activeTemplateId)}
              download
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-colors cursor-pointer text-[11px] shadow-sm"
            >
              <Download className="w-3.5 h-3.5" />
              Download .docx
            </a>
          </div>
        </div>

        {/* Paper Sheet Preview Container */}
        <div
          className={`bg-slate-950/80 border-x border-b border-white/10 rounded-b-2xl p-4 sm:p-8 overflow-y-auto ${
            isFullScreen ? "max-h-[85vh]" : "max-h-[580px]"
          } transition-all duration-300 shadow-inner`}
        >
          {/* Actual Document Sheet */}
          <div
            className={`w-full max-w-3xl mx-auto rounded-xl p-6 sm:p-10 shadow-2xl transition-all duration-300 ${theme.paperClass}`}
            style={{ fontFamily: theme.fontFamily }}
          >
            {/* Header: Candidate Identity */}
            {activeTemplateId === "default" ? (
              <div className="pb-3 mb-4">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                  <div>
                    <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
                      {candidateName}
                    </h1>
                    <p className="text-xs text-slate-600 mt-1 font-medium">{city}</p>
                  </div>
                  <div className="text-left sm:text-right text-xs text-slate-600 space-y-1 font-medium">
                    <p>
                      {personal.email || "email@example.com"}
                      {personal.linkedin && (
                        <span>
                          {" "} | <span className="text-blue-600 underline">LinkedIn®</span>
                        </span>
                      )}
                      {personal.phone && <span> | {personal.phone}</span>}
                    </p>
                    <p>
                      {personal.github && (
                        <span className="text-blue-600 underline">GitHub</span>
                      )}
                      {personal.github && personal.portfolio && <span> | </span>}
                      {personal.portfolio && (
                        <span className="text-blue-600 underline">
                          {personal.portfolio.replace(/https?:\/\//, "")}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                {/* Horizontal divider rule matching Word template */}
                <div className="w-full h-[1.5px] bg-slate-400 mt-3" />
              </div>
            ) : (
              <div className="text-center pb-4 mb-4 border-b border-slate-200">
                <h1
                  className="text-2xl sm:text-3xl font-extrabold tracking-tight"
                  style={{ color: theme.nameColor }}
                >
                  {candidateName}
                </h1>

                {/* Contact details row */}
                <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-xs text-slate-600 mt-2 font-medium">
                  {contactList.map((c, i) => (
                    <span key={i} className="flex items-center">
                      {i > 0 && <span className="mx-1 text-slate-400">•</span>}
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Professional Summary */}
            {summary && (
              <div className="mb-4">
                <h2 className={theme.sectionHeader}>Professional Summary</h2>
                <p className="text-xs sm:text-[13px] leading-relaxed text-slate-700">
                  {summary}
                </p>
              </div>
            )}

            {/* Technical Skills */}
            {Object.keys(skills).length > 0 && (
              <div className="mb-4">
                <h2 className={theme.sectionHeader}>Technical Skills</h2>
                <div className="space-y-1.5 text-xs sm:text-[13px] text-slate-700">
                  {Object.entries(skills).map(([cat, tags]) => {
                    if (!tags || tags.length === 0) return null;
                    return (
                      <div key={cat} className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-2">
                        <span className="font-bold text-slate-900 capitalize text-xs shrink-0 sm:w-28">
                          {cat}:
                        </span>
                        <span className="text-slate-700 text-xs leading-normal">
                          {tags.join(", ")}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Work Experience */}
            {experience && experience.length > 0 && (
              <div className="mb-4">
                <h2 className={theme.sectionHeader}>Work Experience</h2>
                <div className="space-y-3.5">
                  {experience.map((exp, idx) => {
                    const start = exp.startDate || "";
                    const end = exp.current ? "Present" : exp.endDate || "";
                    const dateStr = [start, end].filter(Boolean).join(" – ");

                    return (
                      <div key={idx} className="text-xs sm:text-[13px]">
                        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between font-bold text-slate-900">
                          <span>
                            {exp.jobTitle || "Software Engineer"}{" "}
                            <span className="font-normal text-slate-600">
                              — {exp.company || "Company"}
                            </span>
                          </span>
                          {dateStr && (
                            <span className="text-slate-500 font-normal text-[11px] sm:text-xs">
                              {dateStr}
                            </span>
                          )}
                        </div>

                        {exp.description && (
                          <p className="text-slate-600 mt-0.5 text-xs italic">
                            {exp.description}
                          </p>
                        )}

                        {exp.responsibilities && exp.responsibilities.length > 0 && (
                          <ul className="list-disc list-outside pl-4 mt-1 space-y-0.5 text-slate-700 text-xs">
                            {exp.responsibilities.map((r, ri) => (
                              <li key={ri}>{r}</li>
                            ))}
                          </ul>
                        )}

                        {/* Sub-projects inside experience */}
                        {exp.projects && exp.projects.length > 0 && (
                          <div className="mt-1.5 pl-3 border-l-2 border-slate-200 space-y-1">
                            {exp.projects.map((sp, spi) => (
                              <div key={spi} className="text-[11px]">
                                <span className="font-semibold text-slate-800">
                                  {sp.name}
                                </span>{" "}
                                {sp.technologies && sp.technologies.length > 0 && (
                                  <span className="text-slate-500">
                                    ({sp.technologies.join(", ")})
                                  </span>
                                )}
                                {sp.achievements && (
                                  <ul className="list-disc pl-3 text-slate-600">
                                    {sp.achievements.map((ach, achi) => (
                                      <li key={achi}>{ach}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Key Projects */}
            {projects && projects.length > 0 && (
              <div className="mb-4">
                <h2 className={theme.sectionHeader}>Key Projects</h2>
                <div className="space-y-2">
                  {projects.map((proj, idx) => (
                    <div key={idx} className="text-xs sm:text-[13px]">
                      <div className="flex items-baseline gap-2">
                        <span className="font-bold text-slate-900">{proj.name}</span>
                        {proj.technologies && proj.technologies.length > 0 && (
                          <span className="text-slate-500 text-[11px]">
                            ({proj.technologies.join(", ")})
                          </span>
                        )}
                      </div>
                      {proj.description && (
                        <p className="text-slate-700 text-xs mt-0.5 pl-3 border-l border-slate-200">
                          {proj.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Education */}
            {education && education.length > 0 && (
              <div className="mb-2">
                <h2 className={theme.sectionHeader}>Education</h2>
                <div className="space-y-1.5">
                  {education.map((edu, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col sm:flex-row sm:items-baseline justify-between text-xs sm:text-[13px]"
                    >
                      <span className="font-bold text-slate-900">
                        {edu.degree || "Degree"}{" "}
                        <span className="font-normal text-slate-600">
                          — {edu.institution || "Institution"}
                        </span>
                      </span>
                      {edu.year && (
                        <span className="text-slate-500 text-[11px] sm:text-xs">
                          {edu.year}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
