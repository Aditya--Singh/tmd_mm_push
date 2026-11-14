import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setToken } from "./api";
import { isEmbed } from "./embed";
import { getHubClient, installBridge, uninstallBridge } from "./hub";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

/** How long the hub is given to hand the session over before the app looks for itself. */
const HUB_WAIT_MS = 4000;

async function embedOrigins(): Promise<string[]> {
  try {
    const meta = await fetch("/api/meta").then((r) => (r.ok ? r.json() : null));
    return meta?.embed_parent_origins ?? [];
  } catch {
    return [];
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    // With login switched off on the server, /api/auth/me answers without a token (default user).
    try {
      setUser(await api.get<User>("/api/auth/me"));
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("sentinel:unauthorized", onUnauthorized);
    return () => window.removeEventListener("sentinel:unauthorized", onUnauthorized);
  }, []);

  // When the app is shown inside the hub, the session arrives over the bridge. The
  // app waits for it before asking for the person, so that it never shows its own
  // sign-in screen for a moment.
  useEffect(() => {
    let cancelled = false;
    let settled = false;

    const settle = async () => {
      if (settled) return;
      settled = true;
      await refresh();
      if (!cancelled) setReady(true);
    };

    const start = async () => {
      const origins = isEmbed() ? await embedOrigins() : [];

      if (cancelled) return;

      if (!origins.length) {
        await settle();
        return;
      }

      installBridge({
        allowedParentOrigins: origins,
        onAuth: async (payload) => {
          if (!payload?.ticket) return;
          try {
            const res = await api.post<{ access_token: string; user: User }>("/api/auth/exchange", {
              ticket: payload.ticket,
            });
            setToken(res.access_token);
            setUser(res.user);
          } catch {
            setUser(null);
          } finally {
            settled = true;
            if (!cancelled) setReady(true);
          }
        },
        onLogout: async () => {
          try {
            await api.post("/api/auth/logout");
          } catch {
            /* the token may already be gone */
          }
          setToken(null);
          setUser(null);
          getHubClient()?.acknowledgeLogout();
        },
      });

      // The app may have been opened on its own, without a hub around it. It must
      // not wait for ever.
      window.setTimeout(() => void settle(), HUB_WAIT_MS);
    };

    void start();

    return () => {
      cancelled = true;
      uninstallBridge();
    };
  }, [refresh]);

  const login = async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>("/api/auth/login", { email, password });
    setToken(res.access_token);
    setUser(res.user);
  };

  const logout = async () => {
    try { await api.post("/api/auth/logout"); } catch { /* token may already be invalid */ }
    setToken(null);
    setUser(null);
  };

  return <Ctx.Provider value={{ user, ready, login, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
}
