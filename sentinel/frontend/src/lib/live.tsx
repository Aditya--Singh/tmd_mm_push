import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { streamSSE } from "./api";

export type LiveEvent = { type: string; [k: string]: any; _at?: number };
type Listener = (ev: LiveEvent) => void;

interface LiveState {
  connected: boolean;
  events: LiveEvent[];
  subscribe: (fn: Listener) => () => void;
}

const Ctx = createContext<LiveState | null>(null);

/** One shared connection to /api/events/stream with automatic reconnect. */
export function LiveProvider({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const listeners = useRef(new Set<Listener>());

  useEffect(() => {
    if (!enabled) return;
    let stop = false;
    let ctrl: AbortController | null = null;
    let delay = 1000;
    const run = async () => {
      while (!stop) {
        ctrl = new AbortController();
        try {
          await streamSSE("/api/events/stream", {
            method: "GET",
            signal: ctrl.signal,
            onEvent: (ev: LiveEvent) => {
              setConnected(true);
              delay = 1000;
              if (ev.type === "hello") {
                setEvents((ev.recent || []).filter((e: LiveEvent) => e.type !== "log").map((e: LiveEvent) => ({ ...e, _at: Date.now() })));
                return;
              }
              const stamped = { ...ev, _at: Date.now() };
              if (ev.type !== "log") setEvents((prev) => [...prev.slice(-199), stamped]);
              listeners.current.forEach((fn) => fn(stamped));
            },
          });
        } catch { /* network drop or abort */ }
        setConnected(false);
        if (stop) break;
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, 15000);
      }
    };
    run();
    return () => {
      stop = true;
      ctrl?.abort();
    };
  }, [enabled]);

  const subscribe = (fn: Listener) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  };

  return <Ctx.Provider value={{ connected, events, subscribe }}>{children}</Ctx.Provider>;
}

export function useLive() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive outside provider");
  return v;
}

export function useLiveListener(fn: Listener, deps: unknown[] = []) {
  const { subscribe } = useLive();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => subscribe(fn), deps);
}
