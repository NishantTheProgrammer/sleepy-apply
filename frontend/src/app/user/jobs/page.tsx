"use client";
import { useEffect, useState, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, MapPin, Building2, Zap, CheckCircle, Loader2, Sparkles,
  ExternalLink, Search, Check, AlertTriangle, FileText, ChevronRight,
  SlidersHorizontal, ChevronLeft, Award, Globe, ShieldCheck, X,
  Eye, Download, RefreshCw, Copy, FileCode, LayoutTemplate, Trash2, Bot, Monitor,
  Mail, Phone, UserCheck, Contact, AlertCircle, Share2, MessageSquare, Plus, Link
} from "lucide-react";
import { jobsApi, type HRContactInfo } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import ReactMarkdown from "react-markdown";

export interface TailoredResumeContent {
  job_id?: string;
  job_title?: string;
  company?: string;
  target_headline?: string;
  tailored_summary?: string;
  matching_skills?: string[];
  required_skills?: string[];
  personal?: {
    name?: string;
    full_name?: string;
    fullName?: string;
    email?: string;
    phone?: string;
    location?: unknown;
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
  summary?: string;
  skills?: Record<string, string[]> | string[];
  experience?: Array<{
    title?: string;
    company?: string;
    location?: unknown;
    start_date?: string;
    end_date?: string;
    current?: boolean;
    description?: string;
    highlights?: string[];
  }>;
  education?: Array<{
    degree?: string;
    field?: string;
    institution?: string;
    year?: string;
    grade?: string;
  }>;
  projects?: Array<{
    title?: string;
    description?: string;
    tech_stack?: string[];
    link?: string;
  }>;
  achievements?: string[];
  template?: string;
  generated_at?: string;
}

interface JobItem {
  _id: string;
  job_id: string;
  user_id: string;
  compatibility_score: number;
  match_reasoning?: string;
  experience_match?: string;
  matching_skills: string[];
  missing_skills: string[];
  score_breakdown?: {
    skills?: number;
    location?: number;
    title?: number;
    experience?: number;
  };
  tailored_resume?: TailoredResumeContent;
  resume_generated_at?: string;
  resume_docx_path?: string;
  job: {
    _id: string;
    title: string;
    company: string;
    location: string | Record<string, unknown>;
    is_remote: boolean;
    application_url: string;
    source?: string;
    source_url?: string;
    description?: string;
    requirements?: string[];
    responsibilities?: string[];
    required_skills?: string[];
    salary_range?: { min?: number; max?: number; currency?: string };
    grade?: string;
    employment_type?: string;
    discovered_at?: string;
    posted_at?: string;
    posted_at_raw?: string;
    hr_contact?: HRContactInfo;
  };
  application?: {
    _id?: string;
    status: string;
    created_at?: string;
    updated_at?: string;
  };
}

function formatLocation(loc: unknown): string {
  if (!loc) return "";
  if (typeof loc === "string") return loc;
  if (typeof loc === "object" && loc !== null) {
    const l = loc as Record<string, unknown>;
    const city = typeof l.city === "string" ? l.city.trim() : "";
    const country = typeof l.country === "string" ? l.country.trim() : "";
    const address = typeof l.address === "string" ? l.address.trim() : "";
    if (city && country) return `${city}, ${country}`;
    if (city) return city;
    if (country) return country;
    if (address) return address;
  }
  return "";
}

function renderFormattedText(text: unknown, customBoldClass?: string) {
  if (!text) return null;
  let str = String(text);
  const projMatch = str.match(/^([A-Za-z0-9.\-,\s/]{2,55}):\s*(.*)$/);
  if (projMatch && !str.startsWith("**") && !str.startsWith("<strong>")) {
    const cleanPrefix = projMatch[1].replace(/\*\*/g, "").trim();
    str = `**${cleanPrefix}:** ${projMatch[2].trim()}`;
  }
  return (
    <ReactMarkdown
      components={{
        strong: ({ children }) => (
          <strong className={customBoldClass || "font-bold text-slate-950 font-black"}>
            {children}
          </strong>
        ),
        b: ({ children }) => (
          <strong className={customBoldClass || "font-bold text-slate-950 font-black"}>
            {children}
          </strong>
        ),
        p: ({ children }) => <span className="inline">{children}</span>,
      }}
    >
      {str}
    </ReactMarkdown>
  );
}

function MarkdownRenderer({
  content,
  className = "",
  boldClassName = "font-bold text-slate-100",
}: {
  content: unknown;
  className?: string;
  boldClassName?: string;
}) {
  if (!content) return null;
  return (
    <div className={`text-xs ${className}`}>
      <ReactMarkdown
        components={{
          strong: ({ children }) => (
            <strong className={boldClassName}>{children}</strong>
          ),
          b: ({ children }) => (
            <strong className={boldClassName}>{children}</strong>
          ),
          p: ({ children }) => (
            <p className="leading-relaxed mb-3 last:mb-0 text-slate-300">{children}</p>
          ),
          h1: ({ children }) => (
            <h1 className="text-sm font-bold text-white mt-3.5 mb-1.5">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xs font-bold text-white mt-3 mb-1 uppercase tracking-wider">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-xs font-semibold text-indigo-300 mt-2.5 mb-1">{children}</h3>
          ),
          ul: ({ children }) => (
            <ul className="space-y-1.5 my-2.5 list-none">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="space-y-1.5 my-2.5 list-decimal list-inside text-slate-300">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="flex items-start gap-2 text-slate-300 leading-relaxed">
              <span className="text-indigo-400 font-bold select-none leading-none mt-1 shrink-0">•</span>
              <span className="flex-1">{children}</span>
            </li>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-400 underline hover:text-indigo-300 transition-colors"
            >
              {children}
            </a>
          ),
        }}
      >
        {String(content)}
      </ReactMarkdown>
    </div>
  );
}

function formatPhoneNumber(phone?: string | null): string {
  if (!phone) return "";
  const clean = phone.replace(/[^0-9]/g, "");
  if (clean.length === 10 && ["6", "7", "8", "9"].includes(clean[0])) {
    return `+91 ${clean.slice(0, 5)} ${clean.slice(5)}`;
  }
  if (clean.startsWith("91") && clean.length === 12) {
    const local = clean.slice(2);
    return `+91 ${local.slice(0, 5)} ${local.slice(5)}`;
  }
  if (phone.startsWith("+91")) return phone;
  return `+91 ${phone.trim()}`;
}

function getWhatsAppUrl(phone: string, text: string): string {
  let clean = phone.replace(/[^0-9]/g, "");
  if (clean.length === 10 && ["6", "7", "8", "9"].includes(clean[0])) {
    clean = "91" + clean;
  } else if (clean.startsWith("0") && clean.length === 11) {
    clean = "91" + clean.slice(1);
  } else if (!clean.startsWith("91") && clean.length === 10) {
    clean = "91" + clean;
  }
  return `https://wa.me/${clean}?text=${encodeURIComponent(text)}`;
}

function renderSourceBadge(source?: string) {
  const s = (source || "career").toLowerCase();
  if (s === "discord_community" || s === "community") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#5865F2]/20 text-[#818cf8] border border-[#5865F2]/40">
        <span className="w-1.5 h-1.5 rounded-full bg-[#5865F2]"></span>
        📌 Community Shared
      </span>
    );
  }
  if (s === "career-crawled") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/15 text-purple-300 border border-purple-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
        Career Crawled
      </span>
    );
  }
  if (s === "linkedin") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/15 text-sky-400 border border-sky-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
        LinkedIn
      </span>
    );
  }
  if (s === "naukri") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
        Naukri
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
      Career Portal
    </span>
  );
}

function getValidJobUrl(job: { application_url?: string; source_url?: string; source?: string; company?: string; title?: string }): string {
  const url = (job.application_url || job.source_url || "").trim();
  if (!url || url === "https://www.naukri.com/" || url === "https://www.naukri.com") {
    if (job.source?.toLowerCase() === "naukri") {
      const comp = (job.company || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const titleWords = (job.title || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .split("-")
        .filter((w) => w && !["and", "or", "in", "to", "of", "the", "a", "for", "with"].includes(w))
        .slice(0, 4)
        .join("-");
      if (comp && titleWords) return `https://www.naukri.com/${comp}-${titleWords}-jobs`;
      if (comp) return `https://www.naukri.com/${comp}-jobs`;
      return `https://www.naukri.com/jobs-in-india?k=${encodeURIComponent(job.title || "software engineer")}`;
    }
    return "#";
  }
  return url;
}

const STATUS_STYLE: Record<string, string> = {
  VERIFIED_SUCCESS: "text-emerald-300 bg-emerald-400/10 border-emerald-400/20",
  APPLIED:          "text-blue-300 bg-blue-400/10 border-blue-400/20",
  APPLYING:         "text-yellow-300 bg-yellow-400/10 border-yellow-400/20",
  FAILED:           "text-red-300 bg-red-400/10 border-red-400/20",
  REQUIRES_USER_ACTION: "text-orange-300 bg-orange-400/10 border-orange-400/20",
};

function JobsPageContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const preselectedId = searchParams.get("selected");

  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState("");

  // Filters & Selected Job
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTab, setFilterTab] = useState<"all" | "delhi_ncr" | "high" | "remote" | "bengaluru" | "whatsapp">("all");
  const [sourceFilter, setSourceFilter] = useState<"all" | "discord_community" | "career-crawled" | "career" | "linkedin" | "naukri">("all");
  const [descExpanded, setDescExpanded] = useState(false);

  // Tailored Resume State & Modal
  const [generatingResumeId, setGeneratingResumeId] = useState<string | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewItem, setPreviewItem] = useState<JobItem | null>(null);
  const [previewTab, setPreviewTab] = useState<"doc" | "json">("doc");
  const [previewTemplate, setPreviewTemplate] = useState<string>("default");
  const [copiedJson, setCopiedJson] = useState(false);
  const [copiedNote, setCopiedNote] = useState<string | null>(null);

  // Auto-Apply Form Filler Review Modal (Dry-Run Preview)
  const [formFillResult, setFormFillResult] = useState<{
    job_id: string;
    job_title: string;
    company: string;
    target_url: string;
    fields_filled: Array<{ field: string; value: string; type: string }>;
    submit_button_found: boolean;
    screenshot_base64?: string;
    screenshot_path?: string;
    message: string;
  } | null>(null);

  // Visible Browser (Headless: False) State
  const [launchingVisibleId, setLaunchingVisibleId] = useState<string | null>(null);
  const [visibleToast, setVisibleToast] = useState<{ company: string; message: string } | null>(null);

  // HR Contact Finder Agent State
  const [findingHRId, setFindingHRId] = useState<string | null>(null);

  const handleFindHRContact = async (jobId: string) => {
    setFindingHRId(jobId);
    try {
      const res = await jobsApi.findHRContact(jobId);
      if (res.ok && res.hr_contact) {
        setJobs((prev) =>
          prev.map((item) => {
            if (item.job._id === jobId || item._id === jobId || item.job_id === jobId) {
              return {
                ...item,
                job: {
                  ...item.job,
                  hr_contact: res.hr_contact,
                },
              };
            }
            return item;
          })
        );
      }
    } catch (err) {
      console.error("Failed to find HR contact:", err);
    } finally {
      setFindingHRId(null);
    }
  };

  // Share to Discord Thread State
  const [sharingDiscordId, setSharingDiscordId] = useState<string | null>(null);
  const [sharedDiscordSuccess, setSharedDiscordSuccess] = useState<{ id: string; url?: string } | null>(null);

  const handleShareToDiscord = async (jobId: string, note?: string) => {
    setSharingDiscordId(jobId);
    try {
      const res = await jobsApi.shareJobToDiscord(jobId, note);
      if (res.ok) {
        setSharedDiscordSuccess({ id: jobId, url: res.thread_url });
        setTimeout(() => setSharedDiscordSuccess(null), 8000);
      }
    } catch (err) {
      console.error("Failed to share job to Discord:", err);
    } finally {
      setSharingDiscordId(null);
    }
  };

  // Add Job from URL Modal State
  const [addJobModalOpen, setAddJobModalOpen] = useState(false);
  const [addJobUrl, setAddJobUrl] = useState("");
  const [addJobNotes, setAddJobNotes] = useState("");
  const [addJobBroadcastDiscord, setAddJobBroadcastDiscord] = useState(true);
  const [addingJob, setAddingJob] = useState(false);
  const [addJobError, setAddJobError] = useState<string | null>(null);

  const handleAddJobByUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addJobUrl.trim()) return;
    setAddingJob(true);
    setAddJobError(null);
    try {
      const res = await jobsApi.addJobByUrl({
        url: addJobUrl.trim(),
        notes: addJobNotes.trim() || undefined,
        broadcast_discord: addJobBroadcastDiscord,
      });
      if (res.ok) {
        setAddJobModalOpen(false);
        setAddJobUrl("");
        setAddJobNotes("");
        await load(1, sourceFilter);
        if (res.job_id) {
          setSelectedJobId(res.job_id);
        }
      } else {
        setAddJobError(res.message || "Failed to add job from URL.");
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Failed to add job from URL. Please check the link.";
      setAddJobError(errMsg);
    } finally {
      setAddingJob(false);
    }
  };

  const load = async (p = 1, src: string = sourceFilter, query: string = searchQuery) => {
    setLoading(true);
    try {
      const res = await jobsApi.list({
        page: p,
        limit: 1000,
        min_score: 50,
        source: src,
        search: query.trim() || undefined,
      });
      const items = (res.items || []) as JobItem[];
      setJobs(items);
      setTotal(res.total || items.length);
      setPage(p);

      // Default select the requested job from query or the first job
      if (items.length > 0) {
        if (preselectedId) {
          const found = items.find((j) => j.job._id === preselectedId || j._id === preselectedId);
          setSelectedJobId(found ? found.job._id : items[0].job._id);
        } else {
          setSelectedJobId((prev) =>
            prev && items.some((j) => j.job._id === prev || j._id === prev) ? prev : items[0].job._id
          );
        }
      } else {
        setSelectedJobId(null);
      }
    } catch (err) {
      console.warn("Failed to load user jobs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setSelectedJobId(null);
    const timer = setTimeout(() => {
      load(1, sourceFilter, searchQuery);
    }, 250);
    return () => clearTimeout(timer);
  }, [user?.id, sourceFilter, searchQuery]);

  const handleDiscoverJobs = async () => {
    setDiscovering(true);
    setDiscoverMsg("");
    try {
      const res = await jobsApi.fetchNow();
      setDiscoverMsg(res.message || "Discovery started! Matching jobs to your profile…");

      // Poll every 2 seconds until matched jobs arrive
      let attempts = 0;
      const interval = setInterval(async () => {
        attempts += 1;
        try {
          const fresh = await jobsApi.list({ page: 1, limit: 30, source: sourceFilter });
          const items = (fresh.items || []) as JobItem[];
          if (items.length > 0 || attempts >= 6) {
            clearInterval(interval);
            setJobs(items);
            setTotal(fresh.total || items.length);
            setDiscovering(false);
          }
        } catch {
          if (attempts >= 6) {
            clearInterval(interval);
            setDiscovering(false);
          }
        }
      }, 2000);
    } catch (err: unknown) {
      setDiscoverMsg(err instanceof Error ? err.message : "Failed to trigger discovery");
      setDiscovering(false);
    }
  };

  const [crawlingNcr, setCrawlingNcr] = useState(false);

  const handleCrawlDelhiNcr = async () => {
    setCrawlingNcr(true);
    try {
      const res = await jobsApi.crawlDelhiNcr({ concurrency: 3 });
      setDiscoverMsg(res.message);
      setSourceFilter("career-crawled");
      await load(1);
      setTimeout(() => setDiscoverMsg(""), 8000);
    } catch (err: unknown) {
      setDiscoverMsg(err instanceof Error ? err.message : "Failed to start Delhi NCR crawler");
    } finally {
      setCrawlingNcr(false);
    }
  };

  const handleApply = async (jobId: string) => {
    setApplying(jobId);
    try {
      const targetItem = jobs.find((j) => j.job._id === jobId || j._id === jobId || j.job_id === jobId);
      const res = await jobsApi.autoApplyForm(jobId);
      if ((res as any)?.mode === "visible_desktop") {
        setVisibleToast({
          company: targetItem?.job.company || "Target Company",
          message: res.message || "Visible Chrome window opened on your desktop! Watch the form being autofilled live without submitting.",
        });
        setTimeout(() => setVisibleToast(null), 12000);
        await load(page);
        return;
      }
      setFormFillResult({
        job_id: jobId,
        job_title: targetItem?.job.title || "Position",
        company: targetItem?.job.company || "Company",
        target_url: res.target_url,
        fields_filled: res.fields_filled || [],
        submit_button_found: res.submit_button_found,
        screenshot_base64: res.screenshot_base64,
        screenshot_path: res.screenshot_path,
        message: res.message,
      });
      if (!res.ok) {
        setDiscoverMsg(res.message || "No fillable application form detected on this career portal.");
        setTimeout(() => setDiscoverMsg(""), 10000);
      }
      await load(page);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Auto-apply form filler failed";
      alert(msg);
    } finally {
      setApplying(null);
    }
  };

  const handleApplyVisible = async (jobId: string, directUrl?: string) => {
    setLaunchingVisibleId(jobId);
    try {
      const targetItem = jobs.find((j) => j.job._id === jobId || j._id === jobId || j.job_id === jobId);
      const compName = targetItem?.job.company || "Target Company";
      const res = await jobsApi.applyVisible(jobId);
      setVisibleToast({
        company: compName,
        message: res.message || `Visible Chromium window opened on your screen for ${compName}! Watch the form being autofilled live without submitting.`,
      });
      setTimeout(() => setVisibleToast(null), 12000);
    } catch (err: unknown) {
      console.warn("Direct visible browser launch error", err);
      if (directUrl) {
        window.open(directUrl, "_blank");
      }
    } finally {
      setLaunchingVisibleId(null);
    }
  };

  const handleGenerateResume = async (jobId: string, openPreview = false, templateOverride?: string) => {
    setGeneratingResumeId(jobId);
    try {
      const chosenTemplate = templateOverride || previewTemplate || "default";
      const res = await jobsApi.generateResume(jobId, chosenTemplate);
      if (res.ok && res.tailored_resume) {
        setJobs((prev) =>
          prev.map((item) => {
            if (item.job._id === jobId || item._id === jobId || item.job_id === jobId) {
              const updatedItem: JobItem = {
                ...item,
                tailored_resume: res.tailored_resume as TailoredResumeContent,
                resume_generated_at: res.generated_at,
              };
              if (openPreview) {
                setPreviewItem(updatedItem);
                setPreviewTemplate(chosenTemplate);
                setPreviewModalOpen(true);
              }
              return updatedItem;
            }
            return item;
          })
        );
      }
    } catch (err) {
      console.error("Failed to generate tailored resume:", err);
    } finally {
      setGeneratingResumeId(null);
    }
  };

  const handleOpenPreview = async (item: JobItem) => {
    if (!item.tailored_resume) {
      await handleGenerateResume(item.job._id, true);
    } else {
      setPreviewItem(item);
      setPreviewTemplate(item.tailored_resume.template || "default");
      setPreviewModalOpen(true);
      setPreviewTab("doc");
    }
  };

  const handleDeleteResume = async (jobId: string) => {
    if (!confirm("Are you sure you want to delete this tailored resume variant? You can generate a new one anytime.")) {
      return;
    }
    try {
      await jobsApi.deleteResume(jobId);
      setJobs((prev) =>
        prev.map((item) => {
          if (item.job._id === jobId || item._id === jobId || item.job_id === jobId) {
            const updated = { ...item };
            delete updated.tailored_resume;
            delete updated.resume_generated_at;
            return updated;
          }
          return item;
        })
      );
      setPreviewModalOpen(false);
      setPreviewItem(null);
    } catch (err) {
      console.error("Failed to delete tailored resume:", err);
    }
  };

  const handleCopyJson = (data: unknown) => {
    try {
      navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 2000);
    } catch (e) {
      console.error(e);
    }
  };

  // Filtered jobs list
  const filteredJobs = useMemo(() => {
    return jobs.filter((item) => {
      const q = searchQuery.toLowerCase().trim();
      const jobLoc = formatLocation(item.job.location).toLowerCase();
      const matchesSearch =
        !q ||
        item.job.title.toLowerCase().includes(q) ||
        item.job.company.toLowerCase().includes(q) ||
        jobLoc.includes(q) ||
        (item.job.hr_contact?.phone && item.job.hr_contact.phone.includes(q)) ||
        (item.job.hr_contact?.name && item.job.hr_contact.name.toLowerCase().includes(q)) ||
        (item.job.hr_contact?.email && item.job.hr_contact.email.toLowerCase().includes(q)) ||
        ((q === "whatsapp" || q === "phone" || q === "call" || q === "number") && Boolean(item.job.hr_contact?.phone));

      if (!matchesSearch) return false;

      if (sourceFilter !== "all") {
        const s = (item.job.source || "career").toLowerCase();
        if (s !== sourceFilter) return false;
      }

      if (filterTab === "whatsapp") {
        return Boolean(item.job.hr_contact?.phone);
      }
      if (filterTab === "high") {
        return item.compatibility_score >= 75;
      }
      if (filterTab === "delhi_ncr") {
        const hub = ((item.job as Record<string, unknown>).delhi_ncr_hub as string || "").toLowerCase();
        const isNCR = Boolean((item.job as Record<string, unknown>).is_delhi_ncr);
        return isNCR || !!hub || ["delhi", "gurugram", "gurgaon", "noida", "faridabad", "ghaziabad", "ncr"].some((h) => jobLoc.includes(h));
      }
      if (filterTab === "remote") {
        return item.job.is_remote || jobLoc.includes("remote");
      }
      if (filterTab === "bengaluru") {
        return jobLoc.includes("bengaluru") || jobLoc.includes("bangalore");
      }
      return true;
    });
  }, [jobs, searchQuery, filterTab, sourceFilter]);

  // Currently selected job object
  const selectedItem = useMemo(() => {
    if (!selectedJobId) return filteredJobs[0] || jobs[0] || null;
    return (
      jobs.find((j) => j.job._id === selectedJobId || j._id === selectedJobId) ||
      filteredJobs[0] ||
      null
    );
  }, [selectedJobId, jobs, filteredJobs]);

  return (
    <div className="p-4 sm:p-6 md:p-8 max-w-full min-w-0">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              🇮🇳 India Tech Openings Only
            </span>
            <span className="text-xs text-slate-400">
              {filteredJobs.length} Verified Positions (≥50% Match)
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black gradient-text">Matched Jobs</h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-0.5">
            Active tech openings across Gurugram, Noida, Delhi NCR, Remote (India), and tech hubs.
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap self-start sm:self-auto shrink-0">
          <button
            onClick={() => setAddJobModalOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-sky-600/20 hover:bg-sky-600/30 text-sky-200 border border-sky-500/40 font-bold text-xs shadow-lg shadow-sky-600/20 transition-all cursor-pointer"
            title="Paste any job link (LinkedIn, Naukri, Greenhouse, Lever, etc.) to parse, enrich with HR contacts, match against your profile, and share to Discord"
          >
            <Plus className="w-3.5 h-3.5 text-sky-400" />
            <span>+ Add Job from URL</span>
          </button>

          <button
            onClick={handleCrawlDelhiNcr}
            disabled={crawlingNcr || discovering}
            className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-gradient-to-r from-fuchsia-600/30 to-purple-600/30 hover:from-fuchsia-600/40 hover:to-purple-600/40 text-fuchsia-200 border border-fuchsia-500/40 font-bold text-xs shadow-lg shadow-fuchsia-600/20 transition-all disabled:opacity-50 cursor-pointer"
            title="Crawl top Delhi NCR tech career portals using the AI Browser Agent"
          >
            {crawlingNcr ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bot className="w-3.5 h-3.5 text-fuchsia-400" />}
            {crawlingNcr ? "Crawling Portals…" : "Crawl Delhi NCR"}
          </button>

          <button
            onClick={handleDiscoverJobs}
            disabled={discovering || crawlingNcr}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 cursor-pointer"
          >
            {discovering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {discovering ? "Discovering & Scoring…" : "Discover Jobs Now"}
          </button>
        </div>
      </div>

      {discoverMsg && (
        <div className="mb-6 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300 flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0 text-indigo-400" />
          <span>{discoverMsg}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="glass rounded-2xl p-3 mb-6 flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by job title, company name, or keywords…"
            className="w-full pl-10 pr-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Source & Category Filter Pills */}
        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          {/* Source Tabs */}
          <div className="flex items-center rounded-xl bg-white/5 border border-white/10 p-0.5 shrink-0">
            {[
              { id: "all", label: "All Sources" },
              { id: "discord_community", label: "📌 Community Shared" },
              { id: "career-crawled", label: "🤖 Career Crawled" },
              { id: "career", label: "Career ATS" },
              { id: "linkedin", label: "LinkedIn" },
              { id: "naukri", label: "Naukri" },
            ].map((s) => (
              <button
                key={s.id}
                onClick={() => setSourceFilter(s.id as "all" | "discord_community" | "career-crawled" | "career" | "linkedin" | "naukri")}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  sourceFilter === s.id
                    ? s.id === "discord_community"
                      ? "bg-[#5865F2] text-white shadow-sm"
                      : s.id === "career-crawled"
                      ? "bg-purple-600 text-white shadow-sm"
                      : s.id === "linkedin"
                      ? "bg-sky-600 text-white shadow-sm"
                      : s.id === "naukri"
                      ? "bg-amber-600 text-white shadow-sm"
                      : s.id === "career"
                      ? "bg-emerald-600 text-white shadow-sm"
                      : "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Location & Match Pills */}
          <div className="flex items-center rounded-xl bg-white/5 border border-white/10 p-0.5 shrink-0 flex-wrap gap-1">
            <button
              onClick={() => setFilterTab("all")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTab === "all"
                  ? "bg-white/15 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              All India
            </button>
            <button
              onClick={() => setFilterTab("delhi_ncr")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTab === "delhi_ncr"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Delhi NCR
            </button>
            <button
              onClick={() => setFilterTab("bengaluru")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTab === "bengaluru"
                  ? "bg-purple-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Bengaluru
            </button>
            <button
              onClick={() => setFilterTab("remote")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTab === "remote"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Remote
            </button>
            <button
              onClick={() => setFilterTab("high")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                filterTab === "high"
                  ? "bg-amber-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              ≥75% Match
            </button>
            <button
              onClick={() => setFilterTab("whatsapp")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                filterTab === "whatsapp"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 border border-emerald-500/20"
              }`}
              title="Filter jobs with recruiter WhatsApp or phone number"
            >
              <Phone className="w-3 h-3" />
              WhatsApp / Phone
            </button>
          </div>
        </div>
      </div>

      {/* Main Split-View Layout */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* ── LEFT COLUMN: MASTER JOB LIST (Cols 1-7) ── */}
        <div className="xl:col-span-7 space-y-3">
          {loading || (discovering && filteredJobs.length === 0) ? (
            <div className="glass rounded-2xl p-16 flex flex-col justify-center items-center gap-3 text-slate-400 text-sm">
              <Loader2 className="w-7 h-7 animate-spin text-indigo-500" />
              <span className="font-bold text-white text-base">Evaluating & Matching Jobs…</span>
              <span className="text-xs text-slate-400">Scoring positions against your profile, skills, and HR contacts in real time</span>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="glass rounded-2xl p-10 text-center">
              <Briefcase className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-white mb-1">No jobs match your filter</h3>
              <p className="text-slate-400 text-xs max-w-sm mx-auto mb-5 leading-relaxed">
                Try resetting your search query or refreshing to load newly scored openings.
              </p>
              <button
                onClick={() => {
                  setSearchQuery("");
                  setFilterTab("all");
                  setSourceFilter("all");
                  load(1, "all");
                }}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs text-white font-semibold cursor-pointer shadow-md transition-all"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Reset Filters & Refresh
              </button>
            </div>
          ) : (
            filteredJobs.map((item, i) => {
              const score = item.compatibility_score;
              const isSelected = selectedItem?.job._id === item.job._id;
              const appStatus = item.application?.status;
              const isHigh = score >= 75;
              const isMed = score >= 50 && score < 75;

              return (
                <motion.div
                  key={item._id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.01, 0.2) }}
                  onClick={() => setSelectedJobId(item.job._id)}
                  className={`p-4 rounded-2xl cursor-pointer transition-all relative overflow-hidden ${
                    isSelected
                      ? "glass border-indigo-500 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30 bg-white/[0.08]"
                      : "glass glass-hover hover:border-white/20"
                  }`}
                >
                  {/* Selected Indicator Accent */}
                  {isSelected && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-indigo-500 to-purple-500" />
                  )}

                  <div className="flex items-start gap-3.5">
                    {/* Score Badge */}
                    <div
                      className={`w-12 h-12 shrink-0 rounded-xl flex flex-col items-center justify-center font-black ${
                        isHigh
                          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                          : isMed
                          ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                          : "bg-red-500/15 text-red-400 border border-red-500/30"
                      }`}
                    >
                      <span className="text-base leading-none">{score}</span>
                      <span className="text-[8px] uppercase tracking-wider font-semibold opacity-70">pts</span>
                    </div>

                    {/* Job Summary */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className={`font-bold text-sm truncate ${isSelected ? "text-indigo-300" : "text-white"}`}>
                            {item.job.title}
                          </h3>
                          <div className="flex items-center gap-2 mt-1 text-xs text-slate-400 flex-wrap">
                            <span className="font-semibold text-slate-300 flex items-center gap-1">
                              <Building2 className="w-3 h-3 text-slate-500" /> {item.job.company}
                            </span>
                            <span>•</span>
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3 h-3 text-slate-500" /> {formatLocation(item.job.location) || "Bengaluru, India"}
                            </span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-medium">
                              🇮🇳 India
                            </span>
                            {renderSourceBadge(item.job.source)}
                          </div>
                        </div>

                        {/* Status Tag or Selected Pill */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          {appStatus && (
                            <span className={`text-[10px] px-2 py-0.5 rounded border font-semibold ${STATUS_STYLE[appStatus] || "text-slate-400 bg-white/5 border-white/10"}`}>
                              {appStatus.replace(/_/g, " ")}
                            </span>
                          )}
                          {isSelected && (
                            <span className="hidden sm:inline-flex text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">
                              Viewing
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Experience Match Badge */}
                      {item.experience_match && (
                        <div className="mt-2">
                          <span className="text-[10px] px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-medium">
                            {item.experience_match}
                          </span>
                        </div>
                      )}

                      {/* Matching and Missing Skills */}
                      <div className="mt-2.5 flex flex-wrap gap-1">
                        {(item.matching_skills || []).slice(0, 4).map((s, sIdx) => (
                          <span
                            key={`${item._id}-match-${s}-${sIdx}`}
                            className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 flex items-center gap-0.5"
                          >
                            <Check className="w-2.5 h-2.5" /> {s}
                          </span>
                        ))}
                        {(item.missing_skills || []).slice(0, 2).map((s, sIdx) => (
                          <span
                            key={`${item._id}-miss-${s}-${sIdx}`}
                            className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20"
                          >
                            {s}
                          </span>
                        ))}
                      </div>

                      {/* HR Contact Discovery Bar */}
                      <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between gap-1.5 flex-wrap">
                        {item.job.hr_contact?.email || item.job.hr_contact?.phone ? (
                          <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px] font-semibold">
                              <UserCheck className="w-2.5 h-2.5 text-emerald-400" />
                              <span className="truncate max-w-[110px]">{item.job.hr_contact.name || "Verified Recruiter"}</span>
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" title="Verified Direct Contact" />
                            </span>

                            {item.job.hr_contact.email && (
                              <a
                                href={`mailto:${item.job.hr_contact.email}?subject=${encodeURIComponent(`Application for ${item.job.title}`)}`}
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 border border-blue-500/20 text-[10px] font-medium transition-colors"
                                title={`Email: ${item.job.hr_contact.email}`}
                              >
                                <Mail className="w-2.5 h-2.5 text-blue-400" />
                                <span className="truncate max-w-[130px] font-mono">{item.job.hr_contact.email}</span>
                              </a>
                            )}

                            {item.job.hr_contact.phone && (
                              <a
                                href={getWhatsAppUrl(item.job.hr_contact.phone, `Hi, I am interested in the ${item.job.title} role at ${item.job.company}.`)}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/20 text-[10px] font-medium transition-colors"
                                title={`WhatsApp: ${formatPhoneNumber(item.job.hr_contact.phone)}`}
                              >
                                <Phone className="w-2.5 h-2.5 text-emerald-400" />
                                <span className="font-mono">{formatPhoneNumber(item.job.hr_contact.phone)}</span>
                              </a>
                            )}
                          </div>
                        ) : item.job.hr_contact?.name || (item.job.hr_contact?.recruiters && item.job.hr_contact.recruiters.length > 0) ? (
                          <div className="flex items-center justify-between w-full">
                            <span className="text-[10px] text-sky-400 font-medium flex items-center gap-1 truncate max-w-[140px]">
                              <Contact className="w-2.5 h-2.5 text-sky-400 shrink-0" />
                              <span className="truncate">{item.job.hr_contact.name || `${item.job.hr_contact.recruiters?.length} Recruiters`}</span>
                            </span>
                            <a
                              href={item.job.hr_contact.linkedin || `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(item.job.company + " Talent Acquisition")}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="px-2 py-0.5 rounded bg-sky-500/10 hover:bg-sky-500/20 text-sky-300 border border-sky-500/20 text-[10px] font-medium flex items-center gap-1 transition-all cursor-pointer shrink-0"
                              title={`View ${item.job.hr_contact.name || "recruiter"} on LinkedIn`}
                            >
                              <ExternalLink className="w-2.5 h-2.5" />
                              Recruiter Profile
                            </a>
                          </div>
                        ) : item.job.hr_contact?.linkedin ? (
                          <div className="flex items-center justify-between w-full">
                            <span className="text-[10px] text-slate-500 flex items-center gap-1">
                              <UserCheck className="w-2.5 h-2.5 text-slate-600" /> No direct email published
                            </span>
                            <a
                              href={item.job.hr_contact.linkedin}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="px-2 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/20 text-[10px] font-medium flex items-center gap-1 transition-all cursor-pointer"
                              title={`Find recruiters at ${item.job.company} on LinkedIn`}
                            >
                              <ExternalLink className="w-2.5 h-2.5" />
                              Find on LinkedIn
                            </a>
                          </div>
                        ) : null}
                      </div>

                      {/* Tailored Resume Status & Quick Action */}
                      <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-xs">
                        {item.tailored_resume ? (
                          <div className="flex items-center gap-1.5 text-purple-300">
                            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                            <span className="text-[10px] font-semibold">Tailored Resume Ready</span>
                          </div>
                        ) : (
                          <div className="text-[10px] text-slate-500">
                            No tailored resume yet
                          </div>
                        )}

                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleShareToDiscord(item.job._id);
                            }}
                            disabled={sharingDiscordId === item.job._id}
                            className="p-1.5 rounded-lg bg-[#5865F2]/10 hover:bg-[#5865F2]/20 text-[#818cf8] border border-[#5865F2]/20 text-[10px] transition-all cursor-pointer disabled:opacity-50"
                            title="Share to Discord Channel (#community-found-jobs)"
                          >
                            {sharingDiscordId === item.job._id ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : sharedDiscordSuccess?.id === item.job._id ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Share2 className="w-3 h-3" />
                            )}
                          </button>

                          {item.tailored_resume ? (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenPreview(item);
                              }}
                              className="px-2 py-1 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/20 text-[10px] font-semibold flex items-center gap-1 transition-all cursor-pointer"
                              title="Preview tailored resume and JSON"
                            >
                              <Eye className="w-3 h-3" /> Preview
                            </button>
                          ) : (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleGenerateResume(item.job._id, true);
                              }}
                              disabled={generatingResumeId === item.job._id}
                              className="px-2 py-1 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/20 text-[10px] font-semibold flex items-center gap-1 transition-all cursor-pointer disabled:opacity-50"
                              title="Generate tailored resume"
                            >
                              {generatingResumeId === item.job._id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Sparkles className="w-3 h-3" />
                              )}
                              Tailor Resume
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })
          )}
        </div>

        {/* ── RIGHT COLUMN: JOB INSPECTOR SIDE PANEL (Cols 8-12, Sticky) ── */}
        <div className="xl:col-span-5 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto custom-scrollbar space-y-4">
          {selectedItem ? (
            <AnimatePresence mode="wait">
              <motion.div
                key={selectedItem.job._id}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.15 }}
                className="space-y-4"
              >
                {/* 1. Header & Primary CTA Card */}
                <div className="glass rounded-2xl p-5 border border-indigo-500/20 relative overflow-hidden">
                  <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                        {selectedItem.job.company}
                      </span>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                        🇮🇳 India
                      </span>
                      {selectedItem.job.is_remote && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">
                          Remote
                        </span>
                      )}
                      {renderSourceBadge(selectedItem.job.source)}
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Verified
                    </span>
                  </div>

                  <h2 className="text-xl font-black text-white mb-2 leading-snug">
                    {selectedItem.job.title}
                  </h2>

                  <div className="flex items-center gap-3 text-xs text-slate-400 mb-4 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Building2 className="w-3.5 h-3.5 text-slate-500" /> {selectedItem.job.company}
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-500" /> {formatLocation(selectedItem.job.location) || "Remote"}
                    </span>
                    {selectedItem.job.employment_type && (
                      <>
                        <span>•</span>
                        <span className="capitalize">{selectedItem.job.employment_type}</span>
                      </>
                    )}
                  </div>

                  {/* Primary Action Row */}
                  <div className="flex items-center gap-2 pt-2 border-t border-white/10">
                    <button
                      onClick={() => handleApplyVisible(selectedItem.job._id, getValidJobUrl(selectedItem.job))}
                      disabled={launchingVisibleId === selectedItem.job._id || applying === selectedItem.job._id}
                      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all cursor-pointer disabled:opacity-60"
                      title="Opens real Google Chrome window on your desktop to autofill the form live without submitting"
                    >
                      {launchingVisibleId === selectedItem.job._id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : selectedItem.application?.status === "FORM_FILLED_READY" ? (
                        <CheckCircle className="w-3.5 h-3.5 text-amber-300" />
                      ) : selectedItem.application?.status === "APPLIED" || selectedItem.application?.status === "VERIFIED_SUCCESS" ? (
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-300" />
                      ) : (
                        <Monitor className="w-3.5 h-3.5 text-amber-300" />
                      )}
                      {launchingVisibleId === selectedItem.job._id
                        ? "Opening Chrome on Desktop…"
                        : "One-Click Auto-Apply (Watch Live in Chrome)"}
                    </button>

                    {/* Headless Snapshot Preview Button */}
                    <button
                      onClick={() => handleApply(selectedItem.job._id)}
                      disabled={applying === selectedItem.job._id}
                      className="px-3 py-2.5 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shrink-0"
                      title="Run quick headless background preview snapshot"
                    >
                      {applying === selectedItem.job._id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-400" />
                      ) : (
                        <Bot className="w-3.5 h-3.5 text-slate-400" />
                      )}
                      <span className="hidden sm:inline">Snapshot</span>
                    </button>

                    {selectedItem.tailored_resume ? (
                      <button
                        onClick={() => handleOpenPreview(selectedItem)}
                        className="px-3 py-2.5 rounded-xl border border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer shrink-0"
                        title="Preview tailored resume & JSON"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Resume</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleGenerateResume(selectedItem.job._id, true)}
                        disabled={generatingResumeId === selectedItem.job._id}
                        className="px-3 py-2.5 rounded-xl border border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50 shrink-0"
                        title="Generate tailored resume"
                      >
                        {generatingResumeId === selectedItem.job._id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        <span className="hidden sm:inline">Tailor Resume</span>
                      </button>
                    )}

                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => handleShareToDiscord(selectedItem.job._id)}
                        disabled={sharingDiscordId === selectedItem.job._id}
                        className="px-3 py-2.5 rounded-xl border border-[#5865F2]/30 bg-[#5865F2]/10 hover:bg-[#5865F2]/20 text-[#818cf8] hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                        title="Share this job to Discord Channel (#community-found-jobs)"
                      >
                        {sharingDiscordId === selectedItem.job._id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : sharedDiscordSuccess?.id === selectedItem.job._id ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Share2 className="w-3.5 h-3.5" />
                        )}
                        <span className="hidden sm:inline">
                          {sharingDiscordId === selectedItem.job._id
                            ? "Sharing…"
                            : sharedDiscordSuccess?.id === selectedItem.job._id
                            ? "Shared!"
                            : "Share to Discord"}
                        </span>
                      </button>

                      <a
                        href={getValidJobUrl(selectedItem.job)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`px-3 py-2.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                          selectedItem.job.source === "career-crawled"
                            ? "border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300"
                            : selectedItem.job.source === "linkedin"
                            ? "border-sky-500/30 bg-sky-500/10 hover:bg-sky-500/20 text-sky-300"
                            : selectedItem.job.source === "naukri"
                            ? "border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300"
                            : "border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5"
                        }`}
                        title="Direct link to original posting"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">
                          {selectedItem.job.source === "career-crawled"
                            ? "Career Portal"
                            : selectedItem.job.source === "linkedin"
                            ? "LinkedIn"
                            : selectedItem.job.source === "naukri"
                            ? "Naukri"
                            : "Portal"}
                        </span>
                      </a>
                    </div>
                  </div>

                  {sharedDiscordSuccess?.id === selectedItem.job._id && (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mt-3 p-2.5 rounded-xl bg-[#5865F2]/15 border border-[#5865F2]/30 flex items-center justify-between text-xs text-indigo-200"
                    >
                      <span className="flex items-center gap-1.5 truncate">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span className="truncate">Shared to <strong>#community-found-jobs</strong> channel!</span>
                      </span>
                      <a
                        href={sharedDiscordSuccess.url || "https://discord.com/channels/1569573880262033499/1571831098860638248"}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline font-bold text-white hover:text-indigo-300 flex items-center gap-1 shrink-0 ml-2"
                      >
                        Open Discord <ExternalLink className="w-3 h-3" />
                      </a>
                    </motion.div>
                  )}
                </div>

                {/* 1.5 HR Contact & Recruiter Outreach Card */}
                <div className="glass rounded-2xl p-5 border border-sky-500/20 bg-sky-950/10 relative overflow-hidden">
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-sky-500/20 border border-sky-500/30 flex items-center justify-center text-sky-400">
                        <UserCheck className="w-4 h-4" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-white flex items-center gap-1.5 flex-wrap">
                          HR & Recruiter Intelligence
                          {selectedItem.job.hr_contact?.email || selectedItem.job.hr_contact?.phone ? (
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-medium">
                              Direct Contact Verified
                            </span>
                          ) : (selectedItem.job.hr_contact?.recruiters && selectedItem.job.hr_contact.recruiters.length > 0) || selectedItem.job.hr_contact?.name ? (
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-medium">
                              {selectedItem.job.hr_contact?.recruiters?.length || 1} Recruiter{(selectedItem.job.hr_contact?.recruiters?.length || 1) > 1 ? "s" : ""} Located
                            </span>
                          ) : (
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-500/20 text-slate-400 border border-slate-500/30 font-medium">
                              No Direct Email Listed
                            </span>
                          )}
                        </h3>
                        <p className="text-[11px] text-slate-400">
                          Discovered contact information for direct hiring outreach
                        </p>
                      </div>
                    </div>

                    <button
                      onClick={() => handleFindHRContact(selectedItem.job._id)}
                      disabled={findingHRId === selectedItem.job._id}
                      className="px-2.5 py-1 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 text-sky-300 border border-sky-500/30 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                      title="Run automated web search agent for recruiters"
                    >
                      {findingHRId === selectedItem.job._id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Search className="w-3 h-3" />
                      )}
                      <span>{findingHRId === selectedItem.job._id ? "Searching Web..." : "Find HR on Web"}</span>
                    </button>
                  </div>

                  <div className="space-y-3">
                    {/* A. If genuine direct email or phone was published in JD */}
                    {(selectedItem.job.hr_contact?.email || selectedItem.job.hr_contact?.phone) && (
                      <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 space-y-2">
                        <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-semibold">
                          <CheckCircle className="w-3.5 h-3.5" />
                          <span>Direct JD Application Contact</span>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                          {selectedItem.job.hr_contact.email && (
                            <div className="p-2.5 rounded-lg bg-white/5 border border-white/5 flex items-center justify-between gap-2">
                              <div className="min-w-0">
                                <p className="text-[10px] text-slate-400">Application Email</p>
                                <p className="text-xs font-bold text-blue-300 font-mono truncate">{selectedItem.job.hr_contact.email}</p>
                              </div>
                              <a
                                href={`mailto:${selectedItem.job.hr_contact.email}?subject=${encodeURIComponent(`Application for ${selectedItem.job.title} - ${user?.discord_username || "Candidate"}`)}&body=${encodeURIComponent(`Dear Hiring Team,\n\nI am writing to express my strong interest in the ${selectedItem.job.title} role at ${selectedItem.job.company}.\n\nLooking forward to hearing from you.\n\nBest regards,\n${user?.discord_username || "Candidate"}`)}`}
                                className="px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-bold flex items-center gap-1 shrink-0"
                              >
                                <Mail className="w-3 h-3" /> Email
                              </a>
                            </div>
                          )}
                          {selectedItem.job.hr_contact.phone && (
                            <div className="p-2.5 rounded-lg bg-white/5 border border-white/5 flex items-center justify-between gap-2">
                              <div className="min-w-0">
                                <p className="text-[10px] text-slate-400">Phone / WhatsApp</p>
                                <p className="text-xs font-bold text-emerald-300 font-mono truncate">{formatPhoneNumber(selectedItem.job.hr_contact.phone)}</p>
                              </div>
                              <a
                                href={getWhatsAppUrl(selectedItem.job.hr_contact.phone, `Hi, I am reaching out regarding the ${selectedItem.job.title} opening at ${selectedItem.job.company}.`)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold flex items-center gap-1 shrink-0 cursor-pointer"
                              >
                                <Phone className="w-3 h-3" /> WhatsApp
                              </a>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* B. Discovered Real Recruiters on the Web (Option 1) */}
                    {selectedItem.job.hr_contact?.recruiters && selectedItem.job.hr_contact.recruiters.length > 0 ? (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                            Recruiters Located at {selectedItem.job.company}
                          </p>
                          <span className="text-[10px] text-slate-400">Verified via Public Web Profiles</span>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {selectedItem.job.hr_contact.recruiters.map((rec, rIdx) => (
                            <div
                              key={rIdx}
                              className="p-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.07] border border-white/5 transition-all flex flex-col justify-between gap-2"
                            >
                              <div className="flex items-start gap-2.5">
                                <div className="w-7 h-7 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-300 shrink-0 mt-0.5">
                                  <Contact className="w-3.5 h-3.5" />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <p className="text-xs font-bold text-white truncate">{rec.name}</p>
                                  <p className="text-[11px] text-slate-400 truncate leading-tight mt-0.5">
                                    {rec.designation || "Talent Acquisition"}
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center gap-1.5 pt-1 border-t border-white/5">
                                <a
                                  href={rec.linkedin}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex-1 flex items-center justify-center gap-1 py-1 px-2 rounded-lg bg-[#0a66c2] hover:bg-[#084e96] text-white text-[11px] font-semibold transition-all"
                                >
                                  <ExternalLink className="w-3 h-3" /> Connect on LinkedIn
                                </a>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const firstName = rec.name.split(" ")[0];
                                    const note = `Hi ${firstName}, I noticed the ${selectedItem.job.title} opening at ${selectedItem.job.company} and would love to connect and share how my engineering background aligns with the team's needs!`;
                                    navigator.clipboard.writeText(note);
                                    setCopiedNote(rec.name);
                                    setTimeout(() => setCopiedNote(null), 2500);
                                  }}
                                  className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-[11px] font-medium flex items-center gap-1 transition-all cursor-pointer"
                                  title="Copy personalized LinkedIn connection note"
                                >
                                  {copiedNote === rec.name ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                  <span>{copiedNote === rec.name ? "Copied" : "Note"}</span>
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : selectedItem.job.hr_contact?.name && !selectedItem.job.hr_contact?.email ? (
                      <div className="p-3 rounded-xl bg-white/[0.04] border border-white/5 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-300 shrink-0">
                            <Contact className="w-4 h-4" />
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-bold text-white truncate">{selectedItem.job.hr_contact.name}</p>
                            <p className="text-[11px] text-slate-400 truncate">{selectedItem.job.hr_contact.designation || "Talent Acquisition"}</p>
                          </div>
                        </div>
                        {selectedItem.job.hr_contact.linkedin && (
                          <a
                            href={selectedItem.job.hr_contact.linkedin}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1.5 rounded-lg bg-[#0a66c2] hover:bg-[#084e96] text-white text-xs font-semibold flex items-center gap-1 shrink-0"
                          >
                            <ExternalLink className="w-3.5 h-3.5" /> View Profile
                          </a>
                        )}
                      </div>
                    ) : !selectedItem.job.hr_contact?.email && !selectedItem.job.hr_contact?.phone ? (
                      <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 flex items-start gap-2.5">
                        <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0 mt-0.5">
                          <AlertCircle className="w-3.5 h-3.5" />
                        </div>
                        <div className="text-left flex-1">
                          <p className="text-xs font-semibold text-slate-200">
                            No direct recruiter email in public JD
                          </p>
                          <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                            Click <strong className="text-sky-300">Find HR on Web</strong> above to scan public web profiles for {selectedItem.job.company} recruiters, or use the 1-click search shortcuts below.
                          </p>
                        </div>
                      </div>
                    ) : null}

                    {/* C. Smart Recruiter Outreach Shortcuts (Option 3) */}
                    <div className="pt-2 border-t border-white/5 space-y-2">
                      <p className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
                        <Search className="w-3 h-3 text-indigo-400" />
                        1-Click Recruiter Search Shortcuts
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <a
                          href={selectedItem.job.hr_contact?.linkedin || `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(selectedItem.job.company + " Talent Acquisition OR Recruiter " + (selectedItem.job.location || "India"))}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-white/5 hover:bg-[#0a66c2]/20 border border-white/10 hover:border-[#0a66c2]/40 text-slate-200 hover:text-white font-medium text-xs transition-all cursor-pointer"
                        >
                          <ExternalLink className="w-3.5 h-3.5 text-[#0a66c2]" /> Search Recruiters on LinkedIn
                        </a>
                        <a
                          href={selectedItem.job.hr_contact?.google_search_url || `https://www.google.com/search?q=${encodeURIComponent('site:linkedin.com/in "' + selectedItem.job.company + '" ("Talent Acquisition" OR "Recruiter") ' + (selectedItem.job.location || "India"))}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-white/5 hover:bg-emerald-500/20 border border-white/10 hover:border-emerald-500/40 text-slate-200 hover:text-white font-medium text-xs transition-all cursor-pointer"
                        >
                          <Globe className="w-3.5 h-3.5 text-emerald-400" /> Google Recruiter Search Dork
                        </a>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 2. AI Match Compatibility Breakdown */}
                <div className="glass rounded-2xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-indigo-400" />
                      <h3 className="text-sm font-bold text-white">AI Compatibility Breakdown</h3>
                    </div>
                    <span
                      className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        selectedItem.compatibility_score >= 75
                          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                          : "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                      }`}
                    >
                      {selectedItem.compatibility_score}% Compatibility
                    </span>
                  </div>

                  {/* Seniority & Experience Assessment */}
                  {selectedItem.experience_match && (
                    <div className="mb-3.5 flex items-center gap-2 flex-wrap">
                      <span className="text-[11px] font-medium text-slate-400">Seniority Alignment:</span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                        {selectedItem.experience_match}
                      </span>
                    </div>
                  )}

                  {/* Match reasoning text */}
                  {selectedItem.match_reasoning ? (
                    <div className="p-3 rounded-xl bg-indigo-500/5 border border-indigo-500/15 text-xs text-slate-300 leading-relaxed mb-4">
                      <p className="font-semibold text-indigo-300 text-[11px] mb-1">AI Match Rationale:</p>
                      {selectedItem.match_reasoning}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                      Your technical experience and stack match {selectedItem.compatibility_score}% of the required competencies for this opening at {selectedItem.job.company}.
                    </p>
                  )}

                  {/* Matching Skills */}
                  <div className="mb-4">
                    <p className="text-[10px] uppercase tracking-wider font-semibold text-emerald-400 mb-2 flex items-center gap-1.5">
                      <Check className="w-3 h-3" /> Matching Candidate Skills ({selectedItem.matching_skills.length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedItem.matching_skills.map((skill, skIdx) => (
                        <span
                          key={`sel-match-${skill}-${skIdx}`}
                          className="px-2 py-1 rounded-lg text-xs font-medium bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Missing Skills */}
                  {selectedItem.missing_skills.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider font-semibold text-amber-400 mb-2 flex items-center gap-1.5">
                        <AlertTriangle className="w-3 h-3" /> Missing / Growth Requirements ({selectedItem.missing_skills.length})
                      </p>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {selectedItem.missing_skills.map((skill, skIdx) => (
                          <span
                            key={`sel-miss-${skill}-${skIdx}`}
                            className="px-2 py-1 rounded-lg text-xs font-medium bg-amber-500/10 border border-amber-500/20 text-amber-300"
                          >
                            {skill}
                          </span>
                        ))}
                      </div>
                      <p className="text-[11px] text-slate-500">
                        The AI Resume Tailor will emphasize adjacent experience to bridge these requirements during auto-submission.
                      </p>
                    </div>
                  )}
                </div>

                {/* 3. Tailored Resume & Materials Preview */}
                <div className="glass rounded-2xl p-5 border border-purple-500/20 relative overflow-hidden">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-purple-400" />
                      <h3 className="text-sm font-bold text-white">AI Tailored Resume Variant</h3>
                    </div>
                    {selectedItem.tailored_resume ? (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center gap-1">
                        <Check className="w-2.5 h-2.5" /> Stored in Match Listing
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/10">
                        Not Generated Yet
                      </span>
                    )}
                  </div>

                  {selectedItem.tailored_resume ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>
                          Template:{" "}
                          <strong className="text-slate-200">
                            {selectedItem.tailored_resume.template === "classic_ats" ? "Classic ATS" : "Default Template (Google Doc)"}
                          </strong>
                        </span>
                        {selectedItem.resume_generated_at && (
                          <span className="text-[11px] text-slate-500">
                            {new Date(selectedItem.resume_generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>

                      <div className="p-3 rounded-xl bg-purple-500/5 border border-purple-500/15 text-xs text-slate-300 leading-relaxed">
                        <p className="font-semibold text-purple-300 text-[11px] mb-1.5 flex items-center gap-1.5">
                          <Sparkles className="w-3 h-3 text-purple-400" /> Tailored Profile Pitch:
                        </p>
                        <p className="leading-relaxed">
                          {renderFormattedText(
                            selectedItem.tailored_resume.tailored_summary || selectedItem.tailored_resume.summary,
                            "font-bold text-purple-200"
                          )}
                        </p>
                      </div>

                      {/* Matching Skills Prioritized */}
                      {selectedItem.tailored_resume.matching_skills && selectedItem.tailored_resume.matching_skills.length > 0 && (
                        <div className="text-xs">
                          <p className="text-[10px] uppercase tracking-wider font-semibold text-purple-300 mb-1.5">
                            Prioritized JD Skills ({selectedItem.tailored_resume.matching_skills.length})
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {selectedItem.tailored_resume.matching_skills.map((s, sIdx) => (
                              <span
                                key={`tailored-${s}-${sIdx}`}
                                className="px-1.5 py-0.5 rounded text-[10px] bg-purple-500/10 text-purple-300 border border-purple-500/20"
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Action Buttons */}
                      <div className="pt-2 border-t border-white/5 flex items-center gap-2">
                        <button
                          onClick={() => handleOpenPreview(selectedItem)}
                          className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md shadow-purple-600/20 transition-all cursor-pointer"
                        >
                          <Eye className="w-3.5 h-3.5" /> Preview Resume & JSON
                        </button>

                        <button
                          onClick={() => handleGenerateResume(selectedItem.job._id)}
                          disabled={generatingResumeId === selectedItem.job._id}
                          className="p-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5 transition-all cursor-pointer disabled:opacity-50"
                          title="Regenerate tailored resume"
                        >
                          {generatingResumeId === selectedItem.job._id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                          ) : (
                            <RefreshCw className="w-4 h-4" />
                          )}
                        </button>

                        <a
                          href={jobsApi.getResumeDownloadUrl(selectedItem.job._id)}
                          download
                          className="p-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white hover:bg-white/5 transition-all"
                          title="Download tailored Word document (.docx)"
                        >
                          <Download className="w-4 h-4" />
                        </a>

                        <button
                          onClick={() => handleDeleteResume(selectedItem.job._id)}
                          className="p-2 rounded-xl border border-rose-500/20 hover:border-rose-500/40 text-rose-400 hover:bg-rose-500/10 transition-all cursor-pointer"
                          title="Delete tailored resume"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-4 space-y-3">
                      <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                        Synthesize your candidate profile JSON directly with {selectedItem.job.company}'s requirements to generate an ATS-optimized resume stored against this job match listing.
                      </p>
                      <button
                        onClick={() => handleGenerateResume(selectedItem.job._id, true)}
                        disabled={generatingResumeId === selectedItem.job._id}
                        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition-all cursor-pointer disabled:opacity-50"
                      >
                        {generatingResumeId === selectedItem.job._id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        {generatingResumeId === selectedItem.job._id ? "Synthesizing Resume with AI…" : "Generate Tailored Resume"}
                      </button>
                    </div>
                  )}
                </div>

                {/* 4. Job Description & Responsibilities */}
                {selectedItem.job.description && (
                  <div className="glass rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-bold text-white">Job Description</h3>
                      <button
                        onClick={() => setDescExpanded(!descExpanded)}
                        className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold cursor-pointer"
                      >
                        {descExpanded ? "Collapse" : "Expand All"}
                      </button>
                    </div>

                    <div
                      className={`text-xs text-slate-300 leading-relaxed overflow-hidden transition-all ${
                        descExpanded ? "max-h-none" : "max-h-56 relative"
                      }`}
                    >
                      <MarkdownRenderer content={selectedItem.job.description} />
                      {!descExpanded && (
                        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-slate-950 to-transparent pointer-events-none" />
                      )}
                    </div>

                    {!descExpanded && (
                      <button
                        onClick={() => setDescExpanded(true)}
                        className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 cursor-pointer"
                      >
                        Read full job description <ChevronRight className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          ) : (
            <div className="glass rounded-2xl p-10 text-center">
              <Briefcase className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-sm font-semibold text-white">Select a job to view details</p>
              <p className="text-xs text-slate-400 mt-1">Click on any matched opening on the left to inspect its compatibility breakdown and apply.</p>
            </div>
          )}
        </div>
      </div>

      {/* ── TAILORED RESUME PREVIEW MODAL ── */}
      <AnimatePresence>
        {previewModalOpen && previewItem && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl glass border border-white/10 shadow-2xl overflow-hidden bg-slate-950/95 my-auto"
            >
              {/* Modal Header */}
              <div className="p-4 sm:p-5 border-b border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white/[0.02]">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    {/* Interactive Template Selector */}
                    <div className="flex items-center p-0.5 rounded-lg bg-white/5 border border-white/10">
                      <button
                        onClick={() => {
                          setPreviewTemplate("default");
                          if (previewItem?.tailored_resume) {
                            setPreviewItem({
                              ...previewItem,
                              tailored_resume: {
                                ...previewItem.tailored_resume,
                                template: "default",
                              },
                            });
                          }
                        }}
                        className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                          (previewTemplate || previewItem.tailored_resume?.template || "default") === "default"
                            ? "bg-emerald-600 text-white shadow-sm"
                            : "text-slate-400 hover:text-white"
                        }`}
                        title="Google Doc style template with dual-side header & section divider"
                      >
                        <LayoutTemplate className="w-3 h-3" />
                        <span>Default (Google Doc)</span>
                      </button>
                      <button
                        onClick={() => {
                          setPreviewTemplate("classic_ats");
                          if (previewItem?.tailored_resume) {
                            setPreviewItem({
                              ...previewItem,
                              tailored_resume: {
                                ...previewItem.tailored_resume,
                                template: "classic_ats",
                              },
                            });
                          }
                        }}
                        className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                          (previewTemplate || previewItem.tailored_resume?.template) === "classic_ats"
                            ? "bg-slate-700 text-white shadow-sm"
                            : "text-slate-400 hover:text-white"
                        }`}
                        title="Traditional monochrome serif ATS template"
                      >
                        <ShieldCheck className="w-3 h-3 text-emerald-400" />
                        <span>Classic ATS</span>
                      </button>
                    </div>

                    <span className="text-[10px] font-semibold px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Tailored for {previewItem.job.company}
                    </span>
                    {Array.isArray(previewItem.tailored_resume?.projects) && (
                      <span className="text-[10px] font-semibold px-2 py-1 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                        {previewItem.tailored_resume.projects.length} relevant projects kept
                      </span>
                    )}
                  </div>
                  <h3 className="text-base sm:text-lg font-bold text-white truncate">
                    Tailored Resume: {previewItem.job.title}
                  </h3>
                </div>

                {/* Tabs & Controls */}
                <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                  <div className="flex items-center p-1 rounded-xl bg-white/5 border border-white/10">
                    <button
                      onClick={() => setPreviewTab("doc")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        previewTab === "doc"
                          ? "bg-purple-600 text-white shadow-md shadow-purple-600/20"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <FileText className="w-3.5 h-3.5" />
                      <span>Document Preview</span>
                    </button>
                    <button
                      onClick={() => setPreviewTab("json")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        previewTab === "json"
                          ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/20"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <FileCode className="w-3.5 h-3.5" />
                      <span>Tailored JSON</span>
                    </button>
                  </div>

                  <button
                    onClick={() => setPreviewModalOpen(false)}
                    className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-6 custom-scrollbar bg-slate-900/50">
                {previewTab === "doc" ? (
                  /* ── DOCUMENT PREVIEW TAB (LIVE TEMPLATE PAPER SHEET) ── */
                  <div className="bg-slate-950/70 p-3 sm:p-6 rounded-xl flex justify-center shadow-inner overflow-x-auto">
                    {(() => {
                      const tpl = previewTemplate || previewItem.tailored_resume?.template || "default";
                      const isDefault = tpl === "default";
                      const personal = previewItem.tailored_resume?.personal || {};
                      const candidateName =
                        personal.fullName || personal.full_name || personal.name || "Candidate Name";
                      const locationStr = formatLocation(personal.location);
                      const email = personal.email || "";
                      const phone = personal.phone || "";
                      const linkedin = personal.linkedin || "";
                      const github = personal.github || "";
                      const portfolio = personal.portfolio || "";

                      const contactParts = [
                        email,
                        phone,
                        locationStr,
                        linkedin ? "linkedin.com/in/" + linkedin.replace(/https?:\/\/(www\.)?linkedin\.com\/in\/?/i, "") : null,
                        github ? "github.com/" + github.replace(/https?:\/\/(www\.)?github\.com\/?/i, "") : null,
                        portfolio ? portfolio.replace(/https?:\/\//i, "") : null,
                      ].filter(Boolean);

                      const summaryText =
                        previewItem.tailored_resume?.tailored_summary ||
                        previewItem.tailored_resume?.summary ||
                        "";
                      const skillsData = previewItem.tailored_resume?.skills;
                      const experienceList = previewItem.tailored_resume?.experience || [];
                      const projectsList = previewItem.tailored_resume?.projects || [];
                      const educationList = previewItem.tailored_resume?.education || [];
                      const achievementsList = previewItem.tailored_resume?.achievements || [];

                      const themeStyles = isDefault
                        ? {
                            fontFamily: "Calibri, Arial, sans-serif",
                            paperClass: "bg-white text-slate-800 font-sans",
                            sectionHeader: "font-sans tracking-normal text-slate-900 uppercase text-xs font-black border-b border-slate-300 pb-1 mb-2.5",
                            subText: "text-slate-700",
                          }
                        : {
                            fontFamily: "Times New Roman, serif",
                            paperClass: "bg-white text-black font-serif",
                            sectionHeader: "font-serif text-black uppercase text-xs font-bold border-b border-black pb-0.5 mb-2.5 tracking-wide",
                            subText: "text-black",
                          };

                      return (
                        <div
                          className={`w-full max-w-3xl rounded-lg p-6 sm:p-10 shadow-2xl transition-all duration-300 ${themeStyles.paperClass}`}
                          style={{ fontFamily: themeStyles.fontFamily }}
                        >
                          {/* ── HEADER ── */}
                          {isDefault ? (
                            /* Default Template (Google Doc): Dual-Side Header */
                            <div className="pb-2 mb-4">
                              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                                <div>
                                  <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
                                    {candidateName}
                                  </h1>
                                  {previewItem.tailored_resume?.target_headline && (
                                    <p className="text-xs font-semibold text-indigo-700 tracking-wide mt-0.5">
                                      {previewItem.tailored_resume.target_headline}
                                    </p>
                                  )}
                                  {locationStr && (
                                    <p className="text-xs text-slate-600 mt-1 font-medium">{locationStr}</p>
                                  )}
                                </div>
                                <div className="text-left sm:text-right text-xs text-slate-600 space-y-1 font-medium">
                                  <p>
                                    {email}
                                    {linkedin && (
                                      <span>
                                        {" "} |{" "}
                                        <a
                                          href={linkedin.startsWith("http") ? linkedin : `https://${linkedin}`}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-blue-600 underline"
                                        >
                                          LinkedIn®
                                        </a>
                                      </span>
                                    )}
                                    {phone && <span> | {phone}</span>}
                                  </p>
                                  <p>
                                    {github && (
                                      <a
                                        href={github.startsWith("http") ? github : `https://${github}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 underline"
                                      >
                                        GitHub
                                      </a>
                                    )}
                                    {github && portfolio && <span> | </span>}
                                    {portfolio && (
                                      <a
                                        href={portfolio.startsWith("http") ? portfolio : `https://${portfolio}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 underline"
                                      >
                                        {portfolio.replace(/https?:\/\//, "")}
                                      </a>
                                    )}
                                  </p>
                                </div>
                              </div>
                              {/* Horizontal divider rule matching Google Doc template */}
                              <div className="w-full h-[1.5px] bg-slate-400 mt-3" />
                            </div>
                          ) : (
                            /* Classic ATS: Centered Header */
                            <div className="text-center pb-3 mb-4 border-b border-black">
                              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-black font-serif">
                                {candidateName}
                              </h1>
                              {previewItem.tailored_resume?.target_headline && (
                                <p className="text-xs font-serif italic text-slate-800 mt-1">
                                  {previewItem.tailored_resume.target_headline}
                                </p>
                              )}
                              <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-0.5 text-xs text-black mt-2 font-medium font-serif">
                                {contactParts.map((c, i) => (
                                  <span key={i} className="flex items-center">
                                    {i > 0 && <span className="mx-1.5 text-black">•</span>}
                                    {c}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* ── PROFESSIONAL SUMMARY ── */}
                          {summaryText && (
                            <div className="mb-4">
                              <h2 className={themeStyles.sectionHeader}>
                                {isDefault ? "PROFESSIONAL SUMMARY" : "SUMMARY"}
                              </h2>
                              <p className={`text-xs sm:text-[13px] leading-relaxed ${themeStyles.subText}`}>
                                {renderFormattedText(summaryText)}
                              </p>
                            </div>
                          )}

                          {/* ── TECHNICAL SKILLS / CORE COMPETENCIES ── */}
                          {skillsData && (
                            <div className="mb-4">
                              <h2 className={themeStyles.sectionHeader}>
                                {isDefault ? "CORE COMPETENCIES & SKILLS" : "TECHNICAL SKILLS"}
                              </h2>
                              {typeof skillsData === "object" && !Array.isArray(skillsData) ? (
                                <div className="space-y-1.5 text-xs sm:text-[13px]">
                                  {Object.entries(skillsData).map(([cat, tags]) => {
                                    if (!tags || (Array.isArray(tags) && tags.length === 0)) return null;
                                    const items = Array.isArray(tags) ? tags : [String(tags)];
                                    return (
                                      <div key={cat} className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-2">
                                        <span className="font-bold text-slate-900 shrink-0 sm:w-28 capitalize text-xs">
                                          {cat}:
                                        </span>
                                        <span className={`text-xs leading-normal ${themeStyles.subText}`}>
                                          {items.map((sk, sIdx) => {
                                            const cleanSk = sk.replace(/\*\*/g, "").trim();
                                            const isMatching =
                                              (previewItem.tailored_resume?.matching_skills || []).some(
                                                (m) => m.toLowerCase() === cleanSk.toLowerCase()
                                              ) || sk.startsWith("**");

                                            return (
                                              <span key={sIdx}>
                                                {sIdx > 0 && ", "}
                                                {isMatching ? (
                                                  <strong className="font-bold text-slate-950 font-black">
                                                    {cleanSk}
                                                  </strong>
                                                ) : (
                                                  cleanSk
                                                )}
                                              </span>
                                            );
                                          })}
                                        </span>
                                      </div>
                                    );
                                  })}
                                </div>
                              ) : (
                                <div className="text-xs">
                                  <span className="font-bold text-slate-900 sm:w-28 shrink-0">Skills: </span>
                                  <span className={themeStyles.subText}>
                                    {(Array.isArray(skillsData) ? skillsData : [String(skillsData)]).map((sk, sIdx) => {
                                      const cleanSk = sk.replace(/\*\*/g, "").trim();
                                      const isMatching =
                                        (previewItem.tailored_resume?.matching_skills || []).some(
                                          (m) => m.toLowerCase() === cleanSk.toLowerCase()
                                        ) || sk.startsWith("**");
                                      return (
                                        <span key={sIdx}>
                                          {sIdx > 0 && ", "}
                                          {isMatching ? (
                                            <strong className="font-bold text-slate-950 font-black">
                                              {cleanSk}
                                            </strong>
                                          ) : (
                                            cleanSk
                                          )}
                                        </span>
                                      );
                                    })}
                                  </span>
                                </div>
                              )}
                            </div>
                          )}

                          {/* ── PROFESSIONAL EXPERIENCE ── */}
                          {experienceList.length > 0 && (
                            <div className="mb-4">
                              <h2 className={themeStyles.sectionHeader}>
                                {isDefault ? "PROFESSIONAL EXPERIENCE" : "PROFESSIONAL EXPERIENCE"}
                              </h2>
                              <div className="space-y-3.5">
                                {experienceList.map((exp, idx) => {
                                  const expRecord = exp as Record<string, unknown>;
                                  const title = exp.title || expRecord.jobTitle || "Software Engineer";
                                  const company = exp.company || "";
                                  const start = exp.start_date || expRecord.startDate || "";
                                  const isCurr = exp.current || expRecord.is_current;
                                  const end = isCurr ? "Present" : (exp.end_date || expRecord.endDate || "");
                                  const dateStr = [start, end].filter(Boolean).join(" – ");
                                  const bullets = exp.highlights || expRecord.responsibilities || [];
                                  const rawBullets = Array.isArray(bullets) ? bullets : [];
                                  const subProjects = (expRecord.projects as Array<Record<string, unknown>>) || [];

                                  return (
                                    <div key={idx} className="text-xs sm:text-[13px]">
                                      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between font-bold text-slate-900">
                                        <span>
                                          {String(title)}{" "}
                                          <span className="font-normal text-slate-700">
                                            — {String(company)}
                                            {formatLocation(exp.location) && `, ${formatLocation(exp.location)}`}
                                          </span>
                                        </span>
                                        {dateStr && (
                                          <span className="text-slate-600 font-normal text-[11px] sm:text-xs">
                                            {String(dateStr)}
                                          </span>
                                        )}
                                      </div>

                                      {exp.description && (
                                        <p className="text-slate-700 mt-0.5 text-xs italic">
                                          {renderFormattedText(exp.description)}
                                        </p>
                                      )}

                                      {rawBullets.length > 0 && (
                                        <ul className="list-disc list-outside pl-4 mt-1 space-y-0.5 text-slate-700 text-xs">
                                          {rawBullets.map((r, ri) => (
                                            <li key={ri}>{renderFormattedText(r)}</li>
                                          ))}
                                        </ul>
                                      )}

                                      {subProjects.length > 0 && (
                                        <div className="mt-1.5 pl-3 border-l-2 border-slate-200 space-y-1">
                                          {subProjects.map((sp, spi) => {
                                            const spTech = Array.isArray(sp.technologies) ? sp.technologies : [];
                                            const spAchs = Array.isArray(sp.achievements) ? sp.achievements : [];
                                            return (
                                              <div key={spi} className="text-[11px]">
                                                <span className="font-bold text-slate-950 font-black">
                                                  {String(sp.name || sp.title || "Project")}:
                                                </span>{" "}
                                                {spTech.length > 0 && (
                                                  <span className="text-slate-500">
                                                    ({spTech.join(", ")})
                                                  </span>
                                                )}
                                                {spAchs.length > 0 && (
                                                  <ul className="list-disc pl-3 text-slate-600">
                                                    {spAchs.map((ach, achi) => (
                                                      <li key={achi}>{renderFormattedText(ach)}</li>
                                                    ))}
                                                  </ul>
                                                )}
                                              </div>
                                            );
                                          })}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* ── FEATURED PROJECTS ── */}
                          {projectsList.length > 0 && (
                            <div className="mb-4">
                              <h2 className={themeStyles.sectionHeader}>
                                {isDefault ? "FEATURED PROJECTS" : "PROJECTS"}
                              </h2>
                              <div className="space-y-2.5">
                                {projectsList.map((proj, idx) => {
                                  const projRecord = proj as Record<string, unknown>;
                                  const title = proj.title || projRecord.name || "Project";
                                  const tech = proj.tech_stack || projRecord.technologies || [];
                                  const techArray = Array.isArray(tech) ? tech : [];
                                  const link = proj.link || (typeof projRecord.url === "string" ? projRecord.url : undefined);

                                  return (
                                    <div key={idx} className="text-xs sm:text-[13px]">
                                      <div className="flex items-baseline gap-2">
                                        <span className="font-bold text-slate-900">{String(title)}</span>
                                        {techArray.length > 0 && (
                                          <span className="text-slate-600 text-[11px]">
                                            ({techArray.join(", ")})
                                          </span>
                                        )}
                                        {link ? (
                                          <a
                                            href={String(link)}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-blue-600 underline text-[11px] flex items-center gap-0.5 ml-auto"
                                          >
                                            Link <ExternalLink className="w-2.5 h-2.5" />
                                          </a>
                                        ) : null}
                                      </div>
                                      {proj.description && (
                                        <p className="text-slate-700 text-xs mt-0.5 pl-3 border-l border-slate-200">
                                          {renderFormattedText(proj.description)}
                                        </p>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* ── EDUCATION ── */}
                          {educationList.length > 0 && (
                            <div className="mb-2">
                              <h2 className={themeStyles.sectionHeader}>
                                {isDefault ? "EDUCATION" : "EDUCATION"}
                              </h2>
                              <div className="space-y-1.5">
                                {educationList.map((edu, idx) => {
                                  const eduRecord = edu as Record<string, unknown>;
                                  const degree = edu.degree || "";
                                  const field = edu.field ? ` in ${edu.field}` : "";
                                  const inst = edu.institution || "";
                                  const year = edu.year || eduRecord.graduation_year || "";

                                  return (
                                    <div
                                      key={idx}
                                      className="flex flex-col sm:flex-row sm:items-baseline justify-between text-xs sm:text-[13px]"
                                    >
                                      <span className="font-bold text-slate-900">
                                        {degree}{field}{" "}
                                        <span className="font-normal text-slate-700">
                                          — {inst}
                                        </span>
                                      </span>
                                      {year && (
                                        <span className="text-slate-600 text-[11px] sm:text-xs">
                                          {String(year)}
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* ── ACHIEVEMENTS (Optional) ── */}
                          {achievementsList.length > 0 && (
                            <div className="mb-2">
                              <h2 className={themeStyles.sectionHeader}>ACHIEVEMENTS</h2>
                              <ul className="list-disc list-outside pl-4 mt-1 space-y-0.5 text-slate-700 text-xs">
                                {achievementsList.map((ach, idx) => {
                                  const text = typeof ach === "string" ? ach : (ach as Record<string, unknown>).title || JSON.stringify(ach);
                                  return <li key={idx}>{String(text)}</li>;
                                })}
                              </ul>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                ) : (
                  /* ── TAILORED JSON TAB ── */
                  <div className="space-y-3">
                    <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-indigo-300">
                      <div>
                        <p className="font-semibold text-white">Stored against Job-User Match Listing</p>
                        <p className="text-[11px] text-slate-400">
                          MongoDB collection: <code className="text-indigo-300">db.job_matches.tailored_resume</code>
                        </p>
                      </div>
                      <button
                        onClick={() => handleCopyJson(previewItem.tailored_resume)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all cursor-pointer self-start sm:self-auto"
                      >
                        {copiedJson ? <Check className="w-3.5 h-3.5 text-emerald-300" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedJson ? "Copied JSON!" : "Copy JSON"}</span>
                      </button>
                    </div>

                    <pre className="p-4 rounded-xl bg-black/80 border border-white/10 text-emerald-400 font-mono text-xs overflow-x-auto leading-relaxed max-h-[60vh] custom-scrollbar selection:bg-emerald-500/30">
                      {JSON.stringify(previewItem.tailored_resume, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="p-4 border-t border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white/[0.02]">
                <button
                  onClick={() => setPreviewModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-400 hover:text-white text-xs font-semibold transition-all cursor-pointer"
                >
                  Close
                </button>

                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => handleGenerateResume(previewItem.job._id, true, previewTemplate)}
                    disabled={generatingResumeId === previewItem.job._id}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-white/10 hover:border-white/20 text-slate-300 hover:text-white text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
                  >
                    {generatingResumeId === previewItem.job._id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    <span>Regenerate</span>
                  </button>

                  <a
                    href={jobsApi.getResumeDownloadUrl(previewItem.job._id, previewTemplate)}
                    download
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold transition-all"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download .docx</span>
                  </a>

                  <button
                    onClick={() => handleDeleteResume(previewItem.job._id)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-rose-500/20 hover:border-rose-500/40 text-rose-400 hover:bg-rose-500/10 text-xs font-semibold transition-all cursor-pointer"
                    title="Delete tailored resume"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Delete</span>
                  </button>

                  <button
                    onClick={() => {
                      handleApply(previewItem.job._id);
                      setPreviewModalOpen(false);
                    }}
                    disabled={applying === previewItem.job._id}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all cursor-pointer disabled:opacity-50"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Auto-Apply with this Resume</span>
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── Auto-Apply Form Filler Review Modal (Dry-Run Preview) ── */}
      <AnimatePresence>
        {formFillResult && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="glass rounded-3xl max-w-4xl w-full max-h-[92vh] flex flex-col border border-emerald-500/30 shadow-2xl overflow-hidden bg-slate-950/95"
            >
              {/* Header */}
              <div className="p-4 sm:p-5 border-b border-white/10 flex items-center justify-between bg-emerald-950/20">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                    <CheckCircle className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm sm:text-base font-black text-white">Application Form Autofilled</h3>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                        🛑 Submission Withheld for Review
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {formFillResult.company} • {formFillResult.job_title}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setFormFillResult(null)}
                  className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Body */}
              <div className="p-4 sm:p-6 overflow-y-auto space-y-4">
                {/* Review Mode Banner */}
                <div className="p-3.5 rounded-2xl bg-gradient-to-r from-amber-500/15 via-emerald-500/10 to-amber-500/15 border border-amber-500/30 text-xs">
                  <div className="flex items-start gap-2.5">
                    <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-bold text-amber-200">
                        Form Successfully Pre-Filled by AI Browser Agent
                      </p>
                      <p className="text-slate-300 text-[11px] mt-0.5 leading-relaxed">
                        We navigated to the career portal, filled your candidate details, social URLs, and attached your tailored resume.
                        <strong> The final apply/submit button was intentionally NOT pressed</strong> so you can review and verify before submitting.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Filled Form Screenshot Preview */}
                {formFillResult.screenshot_base64 && (
                  <div className="rounded-2xl border border-white/10 overflow-hidden bg-black/40">
                    <div className="px-3.5 py-2 bg-white/5 border-b border-white/10 flex items-center justify-between text-[11px] text-slate-400">
                      <span className="font-semibold flex items-center gap-1.5 text-slate-300">
                        <Eye className="w-3.5 h-3.5 text-purple-400" />
                        Captured Form Screenshot (Live State)
                      </span>
                      <span className="text-emerald-400 font-bold">Autofill Completed</span>
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                      <img
                        src={formFillResult.screenshot_base64}
                        alt="Autofilled Form Preview"
                        className="w-full object-cover object-top"
                      />
                    </div>
                  </div>
                )}

                {/* Filled Fields Breakdown */}
                <div>
                  <h4 className="text-xs font-bold text-slate-300 mb-2 uppercase tracking-wider">
                    Filled Information ({formFillResult.fields_filled.length} fields)
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    {formFillResult.fields_filled.map((f, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 flex items-center justify-between gap-2"
                      >
                        <span className="text-slate-400 text-[11px] font-medium shrink-0">{f.field}</span>
                        <span className="text-white font-semibold text-right truncate text-[11px]" title={f.value}>
                          {f.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-white/10 bg-slate-900/50 flex flex-col sm:flex-row items-center justify-between gap-3">
                <span className="text-[11px] text-slate-400">
                  Ready to submit? Open the portal and click the final submit button.
                </span>
                <div className="flex items-center gap-2 w-full sm:w-auto flex-wrap">
                  <button
                    onClick={() => {
                      handleApplyVisible(formFillResult.job_id, formFillResult.target_url);
                      setFormFillResult(null);
                    }}
                    className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition-all cursor-pointer"
                  >
                    <Monitor className="w-3.5 h-3.5" />
                    <span>Watch Live in Desktop Chrome</span>
                  </button>
                  <button
                    onClick={() => setFormFillResult(null)}
                    className="flex-1 sm:flex-initial px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold border border-white/10 transition-colors cursor-pointer"
                  >
                    Done Reviewing
                  </button>
                  <a
                    href={formFillResult.target_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs shadow-lg shadow-emerald-600/30 transition-all"
                  >
                    <span>Open Career Portal to Submit</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Add Job from URL Modal */}
      <AnimatePresence>
        {addJobModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="w-full max-w-lg bg-slate-900 border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
            >
              <div className="flex items-center justify-between p-5 border-b border-white/10">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-300 flex items-center justify-center border border-sky-500/30">
                    <Plus className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-white">Add Job from URL</h3>
                    <p className="text-xs text-slate-400">Parse, match against your profile, and share to community</p>
                  </div>
                </div>
                <button
                  onClick={() => setAddJobModalOpen(false)}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleAddJobByUrl} className="p-5 space-y-4">
                {addJobError && (
                  <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-300 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                    <span>{addJobError}</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Job Posting URL <span className="text-red-400">*</span>
                  </label>
                  <div className="relative">
                    <Link className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="url"
                      required
                      placeholder="https://in.linkedin.com/jobs/view/... or Greenhouse / Lever / portal link"
                      value={addJobUrl}
                      onChange={(e) => setAddJobUrl(e.target.value)}
                      className="w-full pl-9 pr-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 transition-all"
                    />
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Supports LinkedIn, Naukri, Greenhouse, Lever, Ashby, and company career pages.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Notes / Referral Context (Optional)
                  </label>
                  <textarea
                    rows={2}
                    placeholder="e.g. Hiring manager is looking for 3+ yrs React experience; referral available"
                    value={addJobNotes}
                    onChange={(e) => setAddJobNotes(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 transition-all resize-none"
                  />
                </div>

                <div className="flex items-center gap-2.5 p-3 rounded-xl bg-[#5865F2]/10 border border-[#5865F2]/20">
                  <input
                    type="checkbox"
                    id="broadcast-discord"
                    checked={addJobBroadcastDiscord}
                    onChange={(e) => setAddJobBroadcastDiscord(e.target.checked)}
                    className="rounded border-white/20 bg-white/5 text-[#5865F2] focus:ring-0 cursor-pointer"
                  />
                  <label htmlFor="broadcast-discord" className="text-xs text-slate-300 cursor-pointer flex-1">
                    Share to Discord channel (<strong>#community-found-jobs</strong>) with 1-click apply buttons
                  </label>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/10">
                  <button
                    type="button"
                    onClick={() => setAddJobModalOpen(false)}
                    className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={addingJob || !addJobUrl.trim()}
                    className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-sky-600/30 transition-all disabled:opacity-50 cursor-pointer"
                  >
                    {addingJob ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                    <span>{addingJob ? "Parsing & Matching Opening…" : "Add & Match Opening"}</span>
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Floating Active Visible Browser Toast Notification */}
      <AnimatePresence>
        {visibleToast && (
          <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            className="fixed top-6 right-6 z-50 max-w-md bg-gradient-to-r from-purple-950/95 to-slate-900/95 border-2 border-purple-500/50 backdrop-blur-xl p-4 rounded-2xl shadow-2xl flex items-start gap-3.5"
          >
            <div className="p-2.5 rounded-xl bg-purple-500/20 text-purple-300 shrink-0 border border-purple-500/30 animate-pulse">
              <ExternalLink className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
                  🖥️ Live Browser Active (Headless: False)
                </h4>
                <button
                  onClick={() => setVisibleToast(null)}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <p className="text-xs text-purple-200 mt-1 leading-relaxed">
                {visibleToast.message}
              </p>
              <p className="text-[11px] text-amber-300/90 mt-1.5 font-medium flex items-center gap-1">
                <span>🛑 Safety:</span> Form autofilled with details & resume. Submit button is held for your review!
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 flex items-center justify-center text-slate-500 text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-indigo-500" /> Loading jobs…
        </div>
      }
    >
      <JobsPageContent />
    </Suspense>
  );
}
