import clsx from "clsx";
import { Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Empty, PageHeader, Spinner, StatusTag, Tag } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate, pct } from "../lib/format";

type Item = { id: number; user: string; rating: number; category: string; tags: string[]; comment: string | null; trace_id: string | null; created_at: string; question: string | null; answer: string | null; verification: string | null };
type Data = { stats: { positive: number; negative: number; satisfaction: number | null; general_avg: number | null; tags: Record<string, number> }; items: Item[] };

export default function Feedback() {
  const { user } = useAuth();
  const [data, setData] = useState<Data | null>(null);
  const [filter, setFilter] = useState<"all" | "neg" | "general">("all");
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const load = () => api.get<Data>("/api/feedback").then(setData).catch((e) => toast.error(e.message));
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!stars) return;
    setSending(true);
    try {
      await api.post("/api/feedback", { rating: stars, category: "general", comment: comment || null });
      toast.success("Thank you — your feedback was recorded.");
      setStars(0);
      setComment("");
      load();
    } catch (e: any) { toast.error(e.message); } finally { setSending(false); }
  };

  const items = (data?.items ?? []).filter((i) => (filter === "neg" ? i.category === "answer" && i.rating < 0 : filter === "general" ? i.category === "general" : true));

  return (
    <div className="pb-10">
      <PageHeader title="Feedback" sub={user?.role === "admin" ? "Ratings from every user, linked to the exact trace that produced each answer." : "Your ratings, linked to the trace behind each answer."} />
      <div className="grid gap-6 px-5 py-5 md:px-8 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          {data && (
            <div className="mb-5 grid grid-cols-2 overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-4">
              {[
                ["Answer satisfaction", pct(data.stats.satisfaction)],
                ["Helpful", data.stats.positive],
                ["Not helpful", data.stats.negative],
                ["Product rating", data.stats.general_avg ? `${data.stats.general_avg} / 5` : "–"],
              ].map(([k, v], i) => (
                <div key={String(k)} className={clsx("px-4 py-3", i > 0 && "border-l border-line", i >= 2 && "max-sm:border-t")}>
                  <div className="text-[12px] text-muted">{k}</div>
                  <div className="font-serif text-[1.6rem] tabular-nums">{v}</div>
                </div>
              ))}
            </div>
          )}
          {data && Object.keys(data.stats.tags).length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-1.5 text-[12.5px]">
              <span className="text-muted">Most reported problems:</span>
              {Object.entries(data.stats.tags).sort((a, b) => b[1] - a[1]).map(([t, n]) => <Tag key={t} tone="bad">{t} · {n}</Tag>)}
            </div>
          )}
          <div className="mb-3 flex gap-1.5">
            {([["all", "All"], ["neg", "Not helpful"], ["general", "Product feedback"]] as const).map(([k, l]) => (
              <button key={k} onClick={() => setFilter(k)} className={clsx("btn btn-sm", filter === k && "border-gold bg-gold-soft text-gold-text")}>{l}</button>
            ))}
          </div>
          {!data ? <Spinner /> : items.length === 0 ? <div className="panel"><Empty title="No feedback here yet">Rate answers with the thumbs buttons in the assistant.</Empty></div> : (
            <ul className="space-y-3">
              {items.map((f) => (
                <li key={f.id} className="panel p-4">
                  <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
                    {f.category === "answer" ? (f.rating > 0 ? <ThumbsUp size={14} className="text-ok" /> : <ThumbsDown size={14} className="text-maroon" />) : <span className="text-gold-text">{"★".repeat(f.rating)}</span>}
                    <span>{f.user}</span><span>·</span><span>{fmtDate(f.created_at, true)}</span>
                    {f.verification && <StatusTag status={f.verification} />}
                    {f.trace_id && <Link className="ml-auto text-link hover:underline" to={`/traces?id=${f.trace_id}`}>Trace</Link>}
                  </div>
                  {f.question && <div className="mt-2 font-serif text-[15px]">{f.question}</div>}
                  {f.answer && <p className="mt-1 line-clamp-3 text-[13px] text-muted">{f.answer}</p>}
                  {f.tags.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{f.tags.map((t) => <Tag key={t} tone={f.rating < 0 ? "bad" : "ok"}>{t}</Tag>)}</div>}
                  {f.comment && <p className="mt-2 border-l-2 border-gold pl-3 text-[13.5px]">{f.comment}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <aside className="panel h-fit p-5">
          <h2 className="text-[1.15rem]">Rate Sentinel</h2>
          <p className="mt-1 text-[13px] text-muted">Tell the team how the tool is working for you overall.</p>
          <div className="mt-3 flex gap-1" role="radiogroup" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} role="radio" aria-checked={stars === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} onClick={() => setStars(n)} className="rounded p-1">
                <Star size={22} className={n <= stars ? "fill-gold text-gold" : "text-line-strong"} />
              </button>
            ))}
          </div>
          <textarea className="textarea mt-3" rows={4} placeholder="What works, what doesn't, what you would add" value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="btn btn-primary mt-3 w-full justify-center" disabled={!stars || sending} onClick={submit}>{sending && <Spinner />} Send feedback</button>
        </aside>
      </div>
    </div>
  );
}
