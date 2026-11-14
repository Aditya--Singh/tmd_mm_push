import clsx from "clsx";
import {
  Activity,
  BookOpenText,
  FileStack,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  MessageSquareText,
  Moon,
  ScrollText,
  Settings,
  ShieldCheck,
  Sun,
  ThumbsUp,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { useAuth } from "../lib/auth";
import { useLive } from "../lib/live";
import { isEmbed } from "../lib/embed";
import { useMeta } from "../lib/meta";
import { Seal } from "./ui";

const GROUPS = [
  {
    label: "Work",
    items: [
      { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
      { to: "/assistant", label: "Assistant", icon: MessageSquareText },
      { to: "/circulars", label: "Circulars", icon: FileStack },
      { to: "/alerts", label: "Alert e-mails", icon: Mail },
    ],
  },
  {
    label: "Oversight",
    items: [
      { to: "/traces", label: "Agent traces", icon: Activity },
      { to: "/logs", label: "Logs", icon: ScrollText, admin: true },
      { to: "/audit", label: "Audit trail", icon: ShieldCheck, admin: true },
      { to: "/feedback", label: "Feedback", icon: ThumbsUp },
    ],
  },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  }, [dark]);
  return [dark, setDark] as const;
}

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const meta = useMeta();
  const embed = isEmbed();
  const visible = (i: { to: string; admin?: boolean }) =>
    (!i.admin || user?.role === "admin") && (i.to !== "/alerts" || meta.email_enabled);
  const { connected } = useLive();
  const [dark, setDark] = useTheme();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);

  const nav = (
    <nav className="flex h-full flex-col border-t-[3px] border-gold bg-ink text-[#ead2d8]">
      <Link to="/" className="flex items-center gap-2.5 px-5 pb-5 pt-5">
        <Seal size={28} />
        <div className="min-w-0 leading-tight">
          <div className="font-serif text-[17px] text-white">Regulatory Sentinel</div>
          <div className="truncate text-[11.5px] text-[#c79aa6]" title={meta.org_name}>{meta.org_name}</div>
        </div>
      </Link>
      <div className="flex-1 overflow-y-auto px-3">
        {GROUPS.map((g) => (
          <div key={g.label} className="mb-4">
            <div className="px-2 pb-1 text-[11.5px] text-[#b98793]">{g.label}</div>
            {g.items
              .filter(visible)
              .map((i) => (
                <NavLink
                  key={i.to}
                  to={i.to}
                  end={"end" in i ? i.end : false}
                  className={({ isActive }) =>
                    clsx(
                      "relative flex items-center gap-2.5 rounded-md px-2 py-[7px] text-[13.5px] transition-colors",
                      isActive ? "bg-white/8 text-white" : "hover:bg-white/5 hover:text-white",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute -left-3 top-1.5 bottom-1.5 w-[3px] rounded-r bg-gold" />}
                      <i.icon size={16} strokeWidth={1.8} className={isActive ? "text-gold" : ""} />
                      {i.label}
                    </>
                  )}
                </NavLink>
              ))}
          </div>
        ))}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            clsx("flex items-center gap-2.5 rounded-md px-2 py-[7px] text-[13.5px]", isActive ? "bg-white/8 text-white" : "hover:bg-white/5 hover:text-white")
          }
        >
          <Settings size={16} strokeWidth={1.8} /> Settings
        </NavLink>
      </div>
      <div className="border-t border-white/10 px-4 py-3">
        <div className="flex items-center gap-2 text-[12px] text-[#c79aa6]" title={connected ? "Receiving live agent activity" : "Reconnecting to live activity"}>
          <span className={clsx("h-1.5 w-1.5 rounded-full", connected ? "bg-[#7fd3a0]" : "bg-[#ff9a9a]")} />
          {connected ? "Live activity connected" : "Live activity reconnecting"}
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[13px] text-white">{user?.name}</div>
            <div className="truncate text-[11.5px] text-[#c79aa6]">{user?.role === "admin" ? "Administrator" : "Analyst"}</div>
          </div>
          <div className="flex">
            <button className="rounded p-1.5 hover:bg-white/10" onClick={() => setDark(!dark)} aria-label={dark ? "Use light theme" : "Use dark theme"}>
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            {meta.auth_enabled && (
              <button className="rounded p-1.5 hover:bg-white/10" onClick={logout} aria-label="Sign out" title="Sign out">
                <LogOut size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </nav>
  );

  if (embed) {
    const items = [...GROUPS.flatMap((g) => g.items), { to: "/settings", label: "Settings", icon: Settings }].filter(visible);
    return (
      <div className="flex h-full flex-col">
        <header className="flex flex-none items-center gap-1 overflow-x-auto border-b border-line bg-surface px-3">
          {items.map((i) => (
            <NavLink
              key={i.to}
              to={i.to}
              end={"end" in i ? i.end : false}
              className={({ isActive }) =>
                clsx(
                  "flex flex-none items-center gap-1.5 border-b-2 px-2.5 py-2.5 text-[13px]",
                  isActive ? "border-gold font-medium text-text" : "border-transparent text-muted hover:text-text",
                )
              }
            >
              <i.icon size={15} strokeWidth={1.8} /> {i.label}
            </NavLink>
          ))}
          <span className="flex-1" />
          <span className={clsx("mr-2 h-1.5 w-1.5 flex-none rounded-full", connected ? "bg-ok" : "bg-maroon")} title={connected ? "Live activity connected" : "Reconnecting"} />
          <button className="btn btn-ghost btn-sm flex-none" onClick={() => setDark(!dark)} aria-label={dark ? "Use light theme" : "Use dark theme"}>
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <aside className="hidden w-[252px] flex-none md:block">{nav}</aside>
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-[260px]">{nav}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-2.5 md:hidden">
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(!open)} aria-label="Open navigation">
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
          <Seal size={20} onDark={false} />
          <span className="font-serif text-[16px]">{meta.org_short} Regulatory Sentinel</span>
        </header>
        {user?.must_change_password && (
          <div className="flex items-center gap-2 border-b border-gold/40 bg-gold-soft px-5 py-2 text-[13px] text-gold-text md:px-8">
            <BookOpenText size={15} />
            You are using a temporary password.
            <Link className="font-medium underline underline-offset-2" to="/settings#password">Change it now</Link>
          </div>
        )}
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
