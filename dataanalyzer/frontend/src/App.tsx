import { useCallback, useEffect, useState } from "react";
import Header from "./components/Header";
import DocumentAssistantPage from "./tabs/document_assistant/DocumentAssistantPage";
import { toolFromHash, toolFromPath, type ToolId } from "./tools";
import { isEmbed } from "./lib/embed";
import { getHubClient, installBridge, setNavigateHandler, uninstallBridge } from "./lib/hub";
import { acknowledgeLogout, forgetToken, setToken } from "./lib/token";

/** How long the hub is given to hand the session over before the app gives up. */
const HUB_WAIT_MS = 4000;

async function embedOrigins(): Promise<string[]> {
  try {
    const meta = await fetch("/api/meta").then((r) => (r.ok ? r.json() : null));
    return meta?.embed_parent_origins ?? [];
  } catch {
    return [];
  }
}

export default function App() {
  const [active, setActive] = useState<ToolId>(() => toolFromHash(window.location.hash));
  const [signedIn, setSignedIn] = useState(false);
  const [waiting, setWaiting] = useState(true);

  useEffect(() => {
    const onHash = () => setActive(toolFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // The hub owns the sign-in. The session arrives over the bridge, and the app waits for
  // it before asking the server who the person is, so that it never shows a sign-in
  // screen of its own for a moment.
  useEffect(() => {
    let cancelled = false;
    let settled = false;

    const settle = () => {
      if (settled) return;
      settled = true;
      if (!cancelled) setWaiting(false);
    };

    const start = async () => {
      const origins = isEmbed() ? await embedOrigins() : [];

      if (cancelled) return;

      if (!origins.length) {
        // The app was opened on its own. There is no hub to sign the person in, so the
        // tool has nothing to show.
        settle();
        return;
      }

      installBridge({
        allowedParentOrigins: origins,
        onAuth: async (payload) => {
          if (!payload?.ticket) return;
          try {
            const response = await fetch("/api/auth/exchange", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ticket: payload.ticket }),
            });

            if (!response.ok) throw new Error("the ticket was refused");

            const body = await response.json();
            setToken(body.access_token ?? "");
            setSignedIn(true);
          } catch {
            forgetToken();
            setSignedIn(false);
          } finally {
            settle();
          }
        },
        onLogout: async () => {
          forgetToken();
          setSignedIn(false);
          acknowledgeLogout();
        },
      });

      // The app may have been opened on its own, without a hub around it. It must not
      // wait for ever.
      window.setTimeout(settle, HUB_WAIT_MS);
    };

    void start();

    return () => {
      cancelled = true;
      uninstallBridge();
    };
  }, []);

  // The hub's rail moves the app between the tools.
  useEffect(() => {
    setNavigateHandler((path: string) => {
      const id = toolFromPath(path);
      if (!id) return;
      window.location.hash = `/${id}`;
      setActive(id);
    });

    return () => setNavigateHandler(null);
  }, []);

  // Tell the hub which tool is on show, so that the rail stays in step.
  useEffect(() => {
    getHubClient()?.reportRoute(`/${active}`);
  }, [active, signedIn]);

  const select = useCallback((id: ToolId) => {
    window.location.hash = `/${id}`;
    setActive(id);
  }, []);

  if (waiting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white text-sm text-slate-500">
        Waiting for the sign-in from the dashboard…
      </div>
    );
  }

  if (!signedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white px-6">
        <div className="max-w-md rounded-lg border border-pnb-gold/40 bg-pnb-cream p-6 text-center">
          <h1 className="text-lg font-semibold text-pnb-maroon">
            Open this from the dashboard
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            This tool is part of the Executive Intelligence Hub, and the hub owns the
            sign-in. Open the Data Analyzer from the dashboard, and it will open here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main
        id={`tool-${active}`}
        className="mx-auto w-full max-w-6xl flex-1 px-6 py-12"
      >
        <DocumentAssistantPage mode={active} onModeChange={select} />
      </main>
      <footer className="border-t border-slate-100 py-6 text-center text-xs text-slate-400">
        Punjab National Bank · For internal use only · All processing happens on this machine
      </footer>
    </div>
  );
}
