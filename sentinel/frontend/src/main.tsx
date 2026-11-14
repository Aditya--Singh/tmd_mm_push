import { StrictMode, useEffect, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router";
import { Toaster } from "sonner";
import { Shell } from "./components/Shell";
import { Spinner } from "./components/ui";
import "@fontsource-variable/source-serif-4/opsz.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-400-italic.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./index.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { isEmbed } from "./lib/embed";
import { getHubClient, setNavigateHandler } from "./lib/hub";
import { LiveProvider } from "./lib/live";
import { useMeta } from "./lib/meta";
import Alerts from "./pages/Alerts";
import Assistant from "./pages/Assistant";
import Audit from "./pages/Audit";
import { CircularList, CircularView } from "./pages/Circulars";
import Feedback from "./pages/Feedback";
import Login from "./pages/Login";
import Logs from "./pages/Logs";
import Overview from "./pages/Overview";
import Settings from "./pages/Settings";
import Traces from "./pages/Traces";

function Protected({ children, admin }: { children: ReactNode; admin?: boolean }) {
  const { user } = useAuth();
  const meta = useMeta();
  if (!user) return meta.auth_enabled ? <Navigate to="/login" replace /> : <div className="grid h-full place-items-center text-muted"><Spinner /></div>;
  if (admin && user.role !== "admin") return <Navigate to="/" replace />;
  return <Shell>{children}</Shell>;
}

/**
 * Keeps the hub and this app in step.
 *
 * The hub may ask for a different screen, and it is told which screen is on show.
 */
function HubRoutes() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    setNavigateHandler((path) => navigate(path));
    return () => setNavigateHandler(null);
  }, [navigate]);

  useEffect(() => {
    getHubClient()?.reportRoute(location.pathname);
  }, [location.pathname]);

  return null;
}

function App() {
  const { ready, user } = useAuth();
  if (!ready) return <div className="grid h-full place-items-center text-muted"><Spinner /></div>;
  return (
    <LiveProvider enabled={!!user}>
      <HubRoutes />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protected><Overview /></Protected>} />
        <Route path="/assistant" element={<Protected><Assistant /></Protected>} />
        <Route path="/circulars" element={<Protected><CircularList /></Protected>} />
        <Route path="/circulars/:id" element={<Protected><CircularView /></Protected>} />
        <Route path="/alerts" element={<Protected><Alerts /></Protected>} />
        <Route path="/traces" element={<Protected><Traces /></Protected>} />
        <Route path="/logs" element={<Protected admin><Logs /></Protected>} />
        <Route path="/audit" element={<Protected admin><Audit /></Protected>} />
        <Route path="/feedback" element={<Protected><Feedback /></Protected>} />
        <Route path="/settings" element={<Protected><Settings /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </LiveProvider>
  );
}

isEmbed(); // read ?embed=1 and ?theme= before the first render

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
        <Toaster position="bottom-right" toastOptions={{ style: { fontFamily: "var(--font-sans)", fontSize: 13.5 } }} />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
