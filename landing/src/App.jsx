import { useCallback, useEffect, useMemo, useState } from "react";

import "./styles/landing.css";

import { me } from "./api/auth";
import { fetchManifest, requestTicket } from "./api/benchmarking";
import FeedbackModal from "./components/FeedbackModal";
import Sidebar from "./components/Sidebar";
import Workspace from "./components/Workspace";
import Login from "./pages/Login";
import { envList } from "./config/env";
import { submitFeedback } from "./api/feedback";
import { createFrameBridge } from "./session/frameBridge";
import {
    readSidebarCollapsed,
    writeSidebarCollapsed,
} from "./session/sidebar";
import {
    clearHubSession,
    readHubSession,
    writeHubSession,
} from "./session/hubSession";
import { servicesForRole, SESSION_MODE } from "./services";

/**
 * Origins an embedded application may be served from when they are not
 * configured explicitly. These are the development and shared-hosting
 * addresses of the news frontend and of Peer Benchmarking.
 */
const DEFAULT_CHILD_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://newsintel.pnbbank.in:5173",
    "http://localhost:8077",
    "http://127.0.0.1:8077",
    "http://newsintel.pnbbank.in:8077",
];

function App() {
    const [session, setSession] = useState(null);
    const [authStatus, setAuthStatus] = useState("resolving");
    const [activeServiceId, setActiveServiceId] = useState(null);

    const [pendingLogout, setPendingLogout] = useState(false);

    const [showFeedback, setShowFeedback] = useState(false);

    // The screens of the service that has its own navigation, keyed by
    // service, and the one that is on show.
    const [sections, setSections] = useState({});
    const [activeSectionId, setActiveSectionId] = useState(null);

    // The single-use sign-in ticket for Peer Benchmarking. It is spent
    // once, so a new one is asked for every time the service is opened.
    const [benchmark, setBenchmark] = useState({ ticket: null, notice: "" });

    const [isCollapsed, setIsCollapsed] = useState(() =>
        readSidebarCollapsed(window.localStorage),
    );

    const clearSession = useCallback(() => {
        clearHubSession(window.localStorage);

        setSession(null);
        setAuthStatus("anonymous");
        setActiveServiceId(null);
        setPendingLogout(false);
        setBenchmark({ ticket: null, notice: "" });
    }, []);

    // The embedded application confirms that it has cleared its session.
    // The frame is only removed afterwards, because a message that is
    // still in flight is lost together with the frame.
    const handleLogoutAck = useCallback(() => {
        clearSession();
    }, [clearSession]);

    // Fall back to clearing the session if the embedded application does
    // not answer, so that signing out can never get stuck.
    useEffect(() => {
        if (!pendingLogout) {
            return undefined;
        }

        const timer = setTimeout(clearSession, 2000);

        return () => clearTimeout(timer);
    }, [pendingLogout, clearSession]);

    const bridge = useMemo(
        () =>
            createFrameBridge({
                allowedChildOrigins: envList(
                    "VITE_ALLOWED_CHILD_ORIGINS",
                    DEFAULT_CHILD_ORIGINS,
                ),
                onChildLogout: clearSession,
                onChildLogoutAck: handleLogoutAck,
            }),
        [clearSession, handleLogoutAck],
    );

    useEffect(() => {
        bridge.install();

        return () => bridge.uninstall();
    }, [bridge]);

    // The workspace decides what the embedded application is handed, so
    // the bridge is not given the session here: the news application
    // shares it, while Peer Benchmarking is given a ticket of its own.

    // Restore a session left over from a previous visit, but only after
    // the backend has confirmed that the token is still valid.
    useEffect(() => {
        let cancelled = false;

        const restore = async () => {
            const stored = readHubSession(window.localStorage);

            if (!stored) {
                if (!cancelled) {
                    setAuthStatus("anonymous");
                }

                return;
            }

            try {
                const user = await me(stored.accessToken);

                if (cancelled) {
                    return;
                }

                setSession({
                    username: user.username,
                    role: user.role,
                    roleLabel: user.role_label ?? stored.roleLabel,
                    accessToken: stored.accessToken,
                });

                setAuthStatus("authenticated");
            } catch {
                clearHubSession(window.localStorage);

                if (!cancelled) {
                    setAuthStatus("anonymous");
                }
            }
        };

        restore();

        return () => {
            cancelled = true;
        };
    }, []);

    // The embedded application tells the hub which screen it moved to,
    // so that the rail follows a journey made inside the application.
    const handleChildRoute = useCallback((payload) => {
        const path = String(payload?.path ?? "").replace(/^#?\/?/, "");

        if (!path) {
            return;
        }

        setActiveSectionId(path);
    }, []);

    const handleToggleSidebar = useCallback(() => {
        setIsCollapsed((previous) => {
            writeSidebarCollapsed(!previous, window.localStorage);

            return !previous;
        });
    }, []);

    const handleLogin = (user) => {
        writeHubSession(user, window.localStorage);

        setSession(user);
        setAuthStatus("authenticated");
    };

    const handleLogout = useCallback(() => {
        const delivered = bridge.notifyChildLogout();

        if (!delivered) {
            clearSession();
            return;
        }

        // Wait for the embedded application to confirm that it has
        // cleared its session before the frame is removed.
        setPendingLogout(true);
    }, [bridge, clearSession]);

    const services = useMemo(
        () => (session ? servicesForRole(session.role) : []),
        [session],
    );

    const activeService = useMemo(
        () => services.find((service) => service.id === activeServiceId),
        [services, activeServiceId],
    );

    // Peer Benchmarking has its own navigation and its own sessions. When
    // it is opened, the hub asks it for the list of screens and for a
    // single-use sign-in ticket for the person who signed in here.
    useEffect(() => {
        if (activeService?.id !== "benchmark") {
            return undefined;
        }

        let cancelled = false;

        const open = async () => {
            try {
                const manifest = await fetchManifest();

                if (cancelled) {
                    return;
                }

                setSections((previous) => ({
                    ...previous,
                    benchmark: manifest.sections ?? [],
                }));

                setActiveSectionId(manifest.defaultSection ?? "overview");

                const ticket = await requestTicket();

                if (cancelled) {
                    return;
                }

                setBenchmark({ ticket: ticket.ticket, notice: "" });
            } catch (err) {
                if (cancelled) {
                    return;
                }

                console.error("Peer Benchmarking could not be opened:", err);

                setBenchmark({
                    ticket: null,
                    notice:
                        err.response?.data?.detail ??
                        "Peer Benchmarking is not available right now.",
                });
            }
        };

        open();

        return () => {
            cancelled = true;
        };
    }, [activeService?.id]);

    // What the embedded application is handed. The news application
    // shares this platform's token; Peer Benchmarking is given a ticket
    // of its own.
    const authPayload = useMemo(() => {
        if (!session || !activeService) {
            return null;
        }

        if (activeService.session === SESSION_MODE.TICKET) {
            if (!benchmark.ticket) {
                return null;
            }

            return {
                username: session.username,
                role: session.role,
                ticket: benchmark.ticket,
            };
        }

        return {
            username: session.username,
            role: session.role,
            accessToken: session.accessToken,
        };
    }, [session, activeService, benchmark.ticket]);

    const activeSection = useMemo(() => {
        const serviceSections = sections?.[activeService?.id] ?? [];

        return (
            serviceSections.find((section) => section.id === activeSectionId) ??
            null
        );
    }, [sections, activeService?.id, activeSectionId]);

    if (authStatus === "resolving") {
        return <div className="loading">Loading Executive Intelligence Hub...</div>;
    }

    if (!session) {
        return <Login onLogin={handleLogin} />;
    }

    const roleLabel =
        session.roleLabel ??
        (session.role === "admin"
            ? "Administrator"
            : session.role.charAt(0).toUpperCase() + session.role.slice(1));

    return (
        <div className="hub">
            <header className="header">
                <div className="header-content">
                    <div>
                        <div className="platform-title">
                            AI-Enabled Top Management Decision Support Platform
                        </div>

                        <div className="platform-subtitle">
                            Unified Executive Intelligence Workspace
                        </div>
                    </div>

                    <div className="header-actions">
                        <div className="header-user">
                            <div className="header-avatar">
                                {session.username.charAt(0).toUpperCase()}
                            </div>

                            <div className="header-user-info">
                                <span>Welcome</span>

                                <strong>{session.username}</strong>
                            </div>
                        </div>

                        <button
                            type="button"
                            className="feedback-header-button"
                            onClick={() => setShowFeedback(true)}
                        >
                            Give Feedback
                        </button>

                        <div className="header-date">
                            {new Date().toLocaleDateString("en-IN", {
                                day: "2-digit",
                                month: "short",
                                year: "numeric",
                            })}
                        </div>

                        <button
                            type="button"
                            className="logout-btn"
                            onClick={handleLogout}
                            title={`Signed in as ${roleLabel}`}
                        >
                            Logout
                        </button>
                    </div>
                </div>
            </header>

            <div className={`container${isCollapsed ? " collapsed" : ""}`}>
                <Sidebar
                    services={services}
                    activeServiceId={activeServiceId}
                    activeSectionId={activeSectionId}
                    sections={sections}
                    isCollapsed={isCollapsed}
                    onToggle={handleToggleSidebar}
                    onSelect={(selected) => {
                        const nextId =
                            selected.id === activeServiceId
                                ? null
                                : selected.id;

                        setActiveServiceId(nextId);

                        // The ticket is spent once, so it is dropped as
                        // soon as the service is closed.
                        if (nextId !== "benchmark") {
                            setBenchmark({ ticket: null, notice: "" });
                        }
                    }}
                    onSelectSection={(section) =>
                        setActiveSectionId(section.id)
                    }
                />

                <main className="main">
                    <Workspace
                        bridge={bridge}
                        service={activeService}
                        session={session}
                        authPayload={authPayload}
                        activeSection={activeSection}
                        onSectionChange={handleChildRoute}
                        notice={
                            activeService?.id === "benchmark"
                                ? benchmark.notice
                                : ""
                        }
                    />
                </main>
            </div>

            {showFeedback && (
                <FeedbackModal
                    onClose={() => setShowFeedback(false)}
                    onSubmit={async (feedback) => {
                        try {
                            await submitFeedback(feedback);

                            setShowFeedback(false);
                        } catch (err) {
                            console.error("Feedback submission failed:", err);

                            setShowFeedback(false);
                        }
                    }}
                />
            )}
        </div>
    );
}

export default App;
