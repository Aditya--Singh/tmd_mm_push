import clsx from "clsx";
import {
  ArrowUp,
  Brain,
  Copy,
  Mail,
  MessagesSquare,
  PanelRight,
  Plus,
  Square,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Markdown } from "../components/Markdown";
import { RoutingSlip } from "../components/RoutingSlip";
import { Seal, Spinner, StatusTag } from "../components/ui";
import { api, streamSSE } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useMeta } from "../lib/meta";
import { relTime } from "../lib/format";
import type { ChatMessage, Conversation, StepEvent, TraceDetail } from "../lib/types";

const SUGGESTIONS = [
  "What is new from the RBI this week, and what needs action?",
  "Summarise the Master Circular on credit facilities to SCs and STs",
  "Under the master direction, when does a term loan become an NPA?",
  "What does the Master Circular on housing finance say about loan-to-value ratios?",
];

const NEG_TAGS = ["Incorrect", "Incomplete", "Not grounded in sources", "Outdated", "Irrelevant"];

export default function Assistant() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [convId, setConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingConv, setLoadingConv] = useState(false);
  const [selected, setSelected] = useState<number | string | null>(null);
  const [activeCite, setActiveCite] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [showConvs, setShowConvs] = useState(false);
  const [showSlip, setShowSlip] = useState(false);
  const [showMemory, setShowMemory] = useState(false);
  const [scope, setScope] = useState<{ id: number; title: string } | null>(null);
  const [includeOlder, setIncludeOlder] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const loadConvs = useCallback(() => api.get<Conversation[]>("/api/conversations").then(setConvs).catch(() => {}), []);
  useEffect(() => { loadConvs(); }, [loadConvs]);

  // "Chat with this circular": /assistant?circular=<id> limits every answer to that one document
  useEffect(() => {
    const cid = params.get("circular");
    if (!cid) return;
    api.get<{ id: number; title: string }>(`/api/circulars/${cid}`)
      .then((c) => { setScope({ id: c.id, title: c.title }); setConvId(null); setMessages([]); setSelected(null); })
      .catch(() => toast.error("That circular could not be found."));
    params.delete("circular");
    setParams(params, { replace: true });
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [params, setParams]);

  // prefill from "Ask the assistant about this" links
  useEffect(() => {
    const q = params.get("q");
    if (q) {
      setInput(q);
      params.delete("q");
      setParams(params, { replace: true });
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [params, setParams]);

  const openConv = async (id: number) => {
    abortRef.current?.abort();
    setShowConvs(false);
    setConvId(id);
    setLoadingConv(true);
    try {
      const c = await api.get<{ messages: ChatMessage[] }>(`/api/conversations/${id}`);
      setMessages(c.messages);
      const lastA = [...c.messages].reverse().find((m) => m.role === "assistant");
      setSelected(lastA?.id ?? null);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setLoadingConv(false);
    }
  };

  const newConv = () => {
    abortRef.current?.abort();
    setConvId(null);
    setMessages([]);
    setSelected(null);
    setShowConvs(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const deleteConv = async (id: number) => {
    if (!confirm("Delete this conversation? Its audit records are kept.")) return;
    await api.del(`/api/conversations/${id}`);
    if (id === convId) newConv();
    loadConvs();
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 240) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const patchMsg = (id: string | number, fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || streaming) return;
    setInput("");
    const uid = `u-${Date.now()}`;
    let aid: string | number = `a-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: uid, role: "user", content, citations: [], meta: {}, trace_id: null },
      { id: aid, role: "assistant", content: "", citations: [], meta: {}, trace_id: null, steps: [], streaming: true },
    ]);
    setSelected(aid);
    setActiveCite(null);
    setStreaming(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamSSE("/api/chat/stream", {
        body: { message: content, conversation_id: convId, circular_id: scope?.id ?? null, include_older: includeOlder },
        signal: ctrl.signal,
        onEvent: (ev) => {
          switch (ev.type) {
            case "meta":
              if (!convId) { setConvId(ev.conversation_id); }
              patchMsg(aid, (m) => ({ ...m, trace_id: ev.trace_id }));
              break;
            case "step":
              patchMsg(aid, (m) => {
                const steps = [...(m.steps || [])];
                const step: StepEvent = { agent: ev.agent, label: ev.label, status: ev.status, detail: ev.detail, ms: ev.ms };
                const idx = steps.findIndex((s) => s.agent === ev.agent && s.label === ev.label && s.status === "running");
                if (idx >= 0 && ev.status !== "running") steps[idx] = step;
                else steps.push(step);
                return { ...m, steps };
              });
              break;
            case "sources":
              patchMsg(aid, (m) => ({ ...m, citations: ev.items }));
              break;
            case "token":
              patchMsg(aid, (m) => ({ ...m, content: m.content + ev.text }));
              break;
            case "replace":
              patchMsg(aid, (m) => ({ ...m, content: ev.text }));
              break;
            case "notice":
              patchMsg(aid, (m) => ({ ...m, notice: ev.text }));
              break;
            case "verification": {
              const { type: _t, ...v } = ev;
              patchMsg(aid, (m) => ({ ...m, meta: { ...m.meta, verification: v } }));
              break;
            }
            case "memory":
              toast("Conversation memory updated", { description: "Older turns were compressed into a summary the agents keep using." });
              break;
            case "done": {
              const newId = ev.message_id;
              patchMsg(aid, (m) => ({ ...m, id: newId, streaming: false, meta: { ...m.meta, intent: ev.intent, actions: ev.actions } }));
              aid = newId;
              setSelected(newId);
              (ev.actions || []).forEach((a: any) => {
                if (a.type === "email") (a.status === "failed" ? toast.error : toast.success)(`E-mail ${a.status === "dry_run" ? "saved to outbox (dry run)" : a.status}`);
              });
              break;
            }
            case "error":
              patchMsg(aid, (m) => ({ ...m, streaming: false, content: m.content || ev.message, notice: ev.message }));
              break;
          }
        },
      });
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        toast.error(e.message || "The request failed.");
        patchMsg(aid, (m) => ({ ...m, content: m.content || "The request failed before the agents could answer.", streaming: false }));
      }
    } finally {
      patchMsg(aid, (m) => ({ ...m, streaming: false }));
      setStreaming(false);
      loadConvs();
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const sel = useMemo(() => messages.find((m) => m.id === selected) ?? null, [messages, selected]);

  // historical messages: rebuild the routing slip from the stored trace
  useEffect(() => {
    if (!sel || sel.role !== "assistant" || sel.streaming || sel.steps?.length || !sel.trace_id) return;
    api.get<TraceDetail>(`/api/traces/${sel.trace_id}`).then((t) => {
      const steps: StepEvent[] = t.spans
        .filter((s) => s.agent !== "LLM")
        .map((s) => ({ agent: s.agent, label: s.name, status: s.status === "ok" ? "done" : s.status === "running" ? "running" : "error", ms: s.duration_ms, detail: compactOutput(s.output) }));
      patchMsg(sel.id, (m) => ({ ...m, steps }));
    }).catch(() => {});
  }, [sel]);

  const onCite = (msgId: number | string, n: number) => {
    setSelected(msgId);
    setActiveCite((c) => (c === n && selected === msgId ? null : n));
    setShowSlip(true);
    setTimeout(() => document.getElementById(`src-${n}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 60);
  };

  const slip = sel && sel.role === "assistant" ? (
    <RoutingSlip
      steps={sel.steps || []}
      verification={sel.meta?.verification}
      sources={sel.citations || []}
      traceId={sel.trace_id}
      activeCite={activeCite}
      onCite={(n) => onCite(sel.id, n)}
      live={sel.streaming}
    />
  ) : (
    <RoutingSlip steps={[]} sources={[]} />
  );

  const convList = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 py-3">
        <span className="font-serif text-[1.05rem]">Conversations</span>
        <button className="btn btn-sm" onClick={newConv}><Plus size={14} /> New</button>
      </div>
      <ul className="flex-1 overflow-y-auto px-2 pb-3">
        {convs.length === 0 && <li className="px-2 py-3 text-[12.5px] text-muted">Your conversations will be listed here.</li>}
        {convs.map((c) => (
          <li key={c.id} className="group relative">
            <button
              onClick={() => openConv(c.id)}
              className={clsx("w-full rounded-md px-2.5 py-2 pr-8 text-left", c.id === convId ? "bg-ink-soft" : "hover:bg-surface-2")}
            >
              <div className="truncate text-[13px] text-text">{c.title}</div>
              <div className="text-[11.5px] text-faint">{relTime(c.updated_at)}{c.has_summary ? " · has memory" : ""}</div>
            </button>
            <button className="absolute right-1.5 top-2.5 hidden rounded p-1 text-faint hover:text-maroon group-hover:block" onClick={() => deleteConv(c.id)} aria-label="Delete conversation">
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );

  return (
    <div className="flex h-full min-h-0">
      {/* conversations */}
      <aside className="hidden w-[248px] flex-none border-r border-line bg-surface lg:block">{convList}</aside>
      {showConvs && (
        <div className="fixed inset-0 z-30 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowConvs(false)} />
          <aside className="absolute inset-y-0 left-0 w-[280px] bg-surface shadow-xl">{convList}</aside>
        </div>
      )}

      {/* chat */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2.5">
          <button className="btn btn-ghost btn-sm lg:hidden" onClick={() => setShowConvs(true)} aria-label="Conversations"><MessagesSquare size={16} /></button>
          <h1 className="min-w-0 flex-1 truncate font-serif text-[1.15rem]">
            {convs.find((c) => c.id === convId)?.title ?? "New conversation"}
          </h1>
          <button className="btn btn-sm" onClick={() => setShowMemory(true)}><Brain size={14} /> Memory</button>
          <button className="btn btn-sm xl:hidden" onClick={() => setShowSlip(true)}><PanelRight size={14} /> Routing slip</button>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          {loadingConv ? (
            <div className="grid h-40 place-items-center text-muted"><Spinner /></div>
          ) : messages.length === 0 ? (
            <div className="mx-auto max-w-2xl px-6 pt-16">
              <Seal size={34} onDark={false} />
              <h2 className="mt-4 text-[1.75rem] leading-tight">Good {greeting()}, {user?.name.split(" ")[0]}.</h2>
              <p className="mt-2 max-w-xl text-[14.5px] text-muted">
                Ask about any indexed RBI circular, Master Circular, Master Direction or press release. Answers cite the paragraph they came from, and the
                routing slip on the right shows which agents handled your question.
              </p>
              <div className="mt-7 grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-lg border border-line bg-surface px-3.5 py-3 text-left text-[13.5px] text-text hover:border-gold">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-[760px] px-4 py-6 md:px-6">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="mb-5 flex justify-end">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-ink px-3.5 py-2.5 text-[14.5px] text-white dark:bg-ink-soft dark:text-text">{m.content}</div>
                  </div>
                ) : (
                  <AssistantMessage
                    key={m.id}
                    m={m}
                    selected={selected === m.id}
                    activeCite={selected === m.id ? activeCite : null}
                    onSelect={() => { setSelected(m.id); setActiveCite(null); }}
                    onCite={(n) => onCite(m.id, n)}
                    onEmail={() => send("Email this answer to me")}
                  />
                ),
              )}
            </div>
          )}
        </div>

        <div className="border-t border-line bg-surface px-4 py-3">
          <div className="mx-auto mb-2 flex max-w-[760px] flex-wrap items-center gap-2 text-[12.5px]">
            {scope ? (
              <span className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-gold/50 bg-gold-soft py-1 pl-2.5 pr-1 text-gold-text">
                <span className="truncate">Only this circular: {scope.title}</span>
                <button className="rounded p-0.5 hover:bg-black/5" onClick={() => setScope(null)} aria-label="Search all circulars again"><X size={13} /></button>
              </span>
            ) : (
              <span className="text-muted">Searching all indexed circulars, master circulars and master directions</span>
            )}
            {!scope && (
              <label className="ml-auto inline-flex items-center gap-1.5 text-muted" title="Master circulars are reissued every year. By default only the latest version of each is searched.">
                <input type="checkbox" checked={includeOlder} onChange={(e) => setIncludeOlder(e.target.checked)} /> Include older yearly versions
              </label>
            )}
          </div>
          <div className="mx-auto flex max-w-[760px] items-end gap-2">
            <textarea
              ref={inputRef}
              className="textarea max-h-40 min-h-[44px] flex-1"
              rows={1}
              placeholder={scope ? "Ask anything about this circular, or say “summarise it”" : "Ask about any circular, master circular or master direction"}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
              }}
              onKeyDown={onKey}
              aria-label="Message"
            />
            {streaming ? (
              <button className="btn h-[44px]" onClick={stop} aria-label="Stop"><Square size={14} /> Stop</button>
            ) : (
              <button className="btn btn-primary h-[44px] w-[44px] justify-center !px-0" onClick={() => send()} disabled={!input.trim()} aria-label="Send">
                <ArrowUp size={18} />
              </button>
            )}
          </div>
          <p className="mx-auto mt-1.5 max-w-[760px] text-[11.5px] text-faint">
            Answers are generated from indexed RBI text and can still be wrong. Check the cited source before acting.
          </p>
        </div>
      </section>

      {/* routing slip */}
      <aside className="hidden w-[340px] flex-none overflow-y-auto border-l border-line bg-surface-2 px-4 py-4 xl:block">{slip}</aside>
      {showSlip && (
        <div className="fixed inset-0 z-30 xl:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowSlip(false)} />
          <aside className="absolute inset-y-0 right-0 w-[min(360px,92vw)] overflow-y-auto bg-surface-2 px-4 py-4 shadow-xl">
            <button className="btn btn-ghost btn-sm mb-2" onClick={() => setShowSlip(false)}><X size={14} /> Close</button>
            {slip}
          </aside>
        </div>
      )}
      {showMemory && <MemoryDrawer onClose={() => setShowMemory(false)} />}
    </div>
  );
}

function greeting() {
  const h = Number(new Date().toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }));
  return h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
}

function compactOutput(o: any): any {
  if (!o || typeof o !== "object") return o;
  if (Array.isArray(o)) return { items: o.length };
  const out: Record<string, any> = {};
  for (const [k, v] of Object.entries(o)) {
    if (["text", "summary", "sentences", "answer"].includes(k)) continue;
    out[k] = typeof v === "object" ? JSON.stringify(v).slice(0, 80) : v;
    if (Object.keys(out).length >= 4) break;
  }
  return out;
}

function AssistantMessage({
  m, selected, activeCite, onSelect, onCite, onEmail,
}: {
  m: ChatMessage;
  selected: boolean;
  activeCite: number | null;
  onSelect: () => void;
  onCite: (n: number) => void;
  onEmail: () => void;
}) {
  const [rating, setRating] = useState<number | null>(null);
  const [askWhy, setAskWhy] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const persisted = typeof m.id === "number";
  const emailOn = useMeta().email_enabled;
  const running = m.steps?.find((s) => s.status === "running");

  const rate = async (r: number, extra?: { tags: string[]; comment: string }) => {
    if (!persisted) return;
    try {
      await api.post("/api/feedback", { message_id: m.id, rating: r, tags: extra?.tags ?? [], comment: extra?.comment || null });
      setRating(r);
      if (r < 0 && !extra) setAskWhy(true);
      else { setAskWhy(false); toast.success("Thanks — feedback recorded against this answer's trace."); }
    } catch (e: any) { toast.error(e.message); }
  };

  return (
    <div className={clsx("group mb-7 rounded-lg border-l-2 pl-4 transition-colors", selected ? "border-gold" : "border-transparent")} onClick={onSelect}>
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-faint">
        <span className="font-medium text-muted">Sentinel</span>
        {m.meta?.intent && <span>· {intentLabel(m.meta.intent)}</span>}
        {m.streaming && running && <span className="text-link">· {running.agent} is working…</span>}
      </div>
      {m.notice && <div className="mb-2 rounded border border-gold/40 bg-gold-soft px-2.5 py-1.5 text-[12.5px] text-gold-text">{m.notice}</div>}
      {m.content ? (
        <Markdown text={m.content} sources={m.citations} activeCite={activeCite} onCite={onCite} streaming={m.streaming} />
      ) : m.streaming ? (
        <div className="flex items-center gap-2 text-[13.5px] text-muted"><Spinner /> {running ? `${running.agent}: ${running.label}` : "Routing your question…"}</div>
      ) : null}

      {!m.streaming && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {m.meta?.verification?.verdict && <StatusTag status={m.meta.verification.verdict} />}
          {m.citations?.length > 0 && <span className="text-[12px] text-faint">{m.citations.length} source{m.citations.length > 1 ? "s" : ""}</span>}
          <span className="flex-1" />
          <div className="flex items-center gap-0.5 opacity-70 group-hover:opacity-100">
            <IconBtn label="Helpful" active={rating === 1} onClick={() => rate(1)} disabled={!persisted}><ThumbsUp size={14} /></IconBtn>
            <IconBtn label="Not helpful" active={rating === -1} onClick={() => rate(-1)} disabled={!persisted}><ThumbsDown size={14} /></IconBtn>
            <IconBtn label="Copy" onClick={() => { navigator.clipboard.writeText(m.content); toast("Copied"); }}><Copy size={14} /></IconBtn>
            {m.meta?.intent === "qa" && emailOn && <IconBtn label="E-mail me this answer" onClick={onEmail}><Mail size={14} /></IconBtn>}
          </div>
        </div>
      )}
      {askWhy && (
        <div className="mt-3 rounded-md border border-line bg-surface p-3" onClick={(e) => e.stopPropagation()}>
          <div className="text-[13px] font-medium">What was wrong?</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {NEG_TAGS.map((t) => (
              <button key={t} className={clsx("rounded border px-2 py-0.5 text-[12px]", tags.includes(t) ? "border-maroon bg-maroon-soft text-maroon" : "border-line text-muted")}
                onClick={() => setTags((p) => (p.includes(t) ? p.filter((x) => x !== t) : [...p, t]))}>{t}</button>
            ))}
          </div>
          <textarea className="textarea mt-2" rows={2} placeholder="Optional: what should the answer have said?" value={comment} onChange={(e) => setComment(e.target.value)} />
          <div className="mt-2 flex justify-end gap-2">
            <button className="btn btn-sm btn-ghost" onClick={() => setAskWhy(false)}>Skip</button>
            <button className="btn btn-sm btn-primary" onClick={() => rate(-1, { tags, comment })}>Send feedback</button>
          </div>
        </div>
      )}
    </div>
  );
}

function IconBtn({ children, label, onClick, active, disabled }: { children: React.ReactNode; label: string; onClick: () => void; active?: boolean; disabled?: boolean }) {
  return (
    <button
      className={clsx("rounded p-1.5 text-muted hover:bg-ink-soft hover:text-text disabled:opacity-40", active && "bg-gold-soft text-gold-text")}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      aria-label={label}
      title={label}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

const intentLabel = (i: string) =>
  ({ qa: "answered from sources", latest: "briefing on recent publications", summarize: "circular summary", email: "e-mail action", remember: "saved to memory", smalltalk: "conversation" } as Record<string, string>)[i] ?? i;

function MemoryDrawer({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<{ notes: { id: number; content: string; created_at: string }[]; conversation_summaries: { conversation_id: number; title: string; summary: string }[] } | null>(null);
  const [note, setNote] = useState("");
  const load = () => api.get<typeof data>("/api/memory").then(setData);
  useEffect(() => { load(); }, []);
  const add = async () => {
    if (note.trim().length < 2) return;
    await api.post("/api/memory", { content: note.trim() });
    setNote("");
    load();
  };
  const del = async (id: number) => { await api.del(`/api/memory/${id}`); load(); };
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-[min(420px,94vw)] flex-col bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-[1.25rem]">Memory</h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <p className="text-[13px] text-muted">
            Notes here are added to every conversation so the agents can tailor answers. Say “remember that…” in chat or add one below. Each change is audited.
          </p>
          <div className="mt-4 flex gap-2">
            <input className="input" placeholder="e.g. I review circulars for the Treasury division" value={note} onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
            <button className="btn" onClick={add}>Add</button>
          </div>
          <h3 className="mt-6 text-[1rem]">Saved notes</h3>
          {!data ? <Spinner /> : data.notes.length === 0 ? <p className="mt-1 text-[13px] text-faint">No notes yet.</p> : (
            <ul className="mt-2 divide-y divide-line">
              {data.notes.map((n) => (
                <li key={n.id} className="flex items-start gap-2 py-2.5 text-[13.5px]">
                  <span className="flex-1">{n.content}<div className="text-[11.5px] text-faint">{relTime(n.created_at)}</div></span>
                  <button className="rounded p-1 text-faint hover:text-maroon" onClick={() => del(n.id)} aria-label="Delete note"><Trash2 size={14} /></button>
                </li>
              ))}
            </ul>
          )}
          <h3 className="mt-6 text-[1rem]">Conversation summaries</h3>
          <p className="text-[12.5px] text-faint">Written by the Memory agent when a conversation grows long, so earlier context is not lost.</p>
          {data?.conversation_summaries.length === 0 && <p className="mt-1 text-[13px] text-faint">None yet.</p>}
          <ul className="mt-2 space-y-3">
            {data?.conversation_summaries.map((c) => (
              <li key={c.conversation_id} className="rounded-md border border-line p-3 text-[13px]">
                <div className="font-medium">{c.title}</div>
                <p className="mt-1 text-muted">{c.summary}</p>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
