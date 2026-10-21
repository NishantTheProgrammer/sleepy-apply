"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard, User, Briefcase, Settings,
  Menu, X, LogOut, ChevronRight, ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useTheme, THEME_CONFIGS } from "@/context/ThemeContext";
import { clsx } from "clsx";

const NAV_ITEMS = [
  { href: "/user/dashboard", label: "Dashboard",  icon: LayoutDashboard },
  { href: "/user/profile",   label: "Profile",     icon: User },
  { href: "/user/jobs",      label: "Jobs",         icon: Briefcase },
  { href: "/user/settings",  label: "Settings",     icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { theme, setTheme, themes } = useTheme();
  const [open, setOpen] = useState(false);

  const avatarUrl = user?.discord_avatar
    ? `https://cdn.discordapp.com/avatars/${user.discord_id}/${user.discord_avatar}.png?size=64`
    : null;

  const NavLinks = () => (
    <nav className="flex flex-col gap-1 px-3">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={() => setOpen(false)}
            className={clsx(
              "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
              active
                ? "bg-white/10 text-white border border-white/15"
                : "text-slate-400 hover:text-white hover:bg-white/5"
            )}
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
            {active && <ChevronRight className="w-3 h-3 ml-auto text-slate-400" />}
          </Link>
        );
      })}

      {user?.role === "admin" && (
        <div className="pt-2 mt-2 border-t border-white/5">
          <Link
            href="/admin"
            onClick={() => setOpen(false)}
            className={clsx(
              "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
              pathname.startsWith("/admin")
                ? "bg-purple-500/20 text-purple-200 border border-purple-500/30"
                : "text-purple-300/70 hover:text-purple-200 hover:bg-purple-500/10"
            )}
          >
            <ShieldCheck className="w-4 h-4 shrink-0 text-purple-400" />
            Admin Panel
            <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 ml-auto border border-purple-500/30">
              Admin
            </span>
          </Link>
        </div>
      )}
    </nav>
  );

  const Brand = () => (
    <div className="px-5 py-5 border-b border-white/10">
      <h1 className="text-lg font-black gradient-text">Sleepy Apply</h1>
      <p className="text-[10px] text-slate-500 mt-0.5">Automated job applications</p>
    </div>
  );

  const UserSection = () => (
    <div className="px-3 mt-auto border-t border-white/10 pt-3 pb-4">
      {user && (
        <div className="flex items-center gap-3 px-3 py-2 rounded-xl glass mb-2">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-8 h-8 rounded-full" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-indigo-600/40 flex items-center justify-center text-xs font-bold text-indigo-200">
              {user.discord_username[0]?.toUpperCase()}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-white truncate">{user.discord_username}</p>
            <p className="text-[10px] text-slate-500 capitalize">{user.role}</p>
          </div>
        </div>
      )}
      {/* Theme picker */}
      <div className="px-3 mb-2">
        <p className="text-[10px] text-slate-500 mb-1.5 font-medium">Theme</p>
        <div className="flex flex-wrap gap-1.5">
          {themes.map((t) => {
            const config = THEME_CONFIGS[t];
            return (
              <button
                key={t}
                onClick={() => setTheme(t)}
                title={`${config.name} (${config.description})`}
                className={clsx(
                  "w-5 h-5 rounded-full border-2 transition-all cursor-pointer shadow-sm",
                  theme === t
                    ? "border-white scale-110 ring-2 ring-white/20"
                    : "border-transparent opacity-60 hover:opacity-100 hover:scale-105"
                )}
                style={{
                  background: `linear-gradient(135deg, ${config.colors[0]}, ${config.colors[1]})`,
                }}
              />
            );
          })}
        </div>
      </div>
      <button
        onClick={logout}
        className="flex items-center gap-2 w-full px-3 py-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/5 text-xs transition-all"
      >
        <LogOut className="w-4 h-4" />
        Sign out
      </button>
    </div>
  );

  return (
    <>
      {/* ── Desktop Sidebar ── */}
      <aside className="hidden lg:flex flex-col fixed left-0 top-0 h-screen w-64 bg-slate-950/80 backdrop-blur border-r border-white/10 z-40">
        <Brand />
        <div className="flex-1 py-4 overflow-y-auto">
          <NavLinks />
        </div>
        <UserSection />
      </aside>

      {/* ── Mobile top bar ── */}
      <header className="lg:hidden fixed top-0 left-0 right-0 h-14 bg-slate-950/90 backdrop-blur border-b border-white/10 z-40 flex items-center px-4 gap-3">
        <button onClick={() => setOpen(true)} className="text-slate-400 hover:text-white">
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="text-sm font-black gradient-text">Sleepy Apply</h1>
      </header>

      {/* ── Mobile drawer ── */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 bg-black/60 z-50 lg:hidden"
            />
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: "spring", damping: 25, stiffness: 250 }}
              className="fixed left-0 top-0 h-screen w-64 bg-slate-950 border-r border-white/10 z-50 lg:hidden flex flex-col"
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
                <h1 className="text-lg font-black gradient-text">Sleepy Apply</h1>
                <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 py-4 overflow-y-auto">
                <NavLinks />
              </div>
              <UserSection />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
