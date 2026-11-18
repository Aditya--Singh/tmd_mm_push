import { useCallback, useEffect, useMemo, useState } from "react";

import "./styles/landing.css";

import { me } from "./api/auth";
import {
    fetchManifest as fetchBenchmarkManifest,
    requestTicket as requestBenchmarkTicket,
} from "./api/benchmarking";
import {
    fetchManifest as fetchSummarizerManifest,
    requestTicket as requestSummarizerTicket,
} from "./api/summarizer";
import {
    fetchManifest as fetchAnalyzerManifest,
    requestTicket as requestAnalyzerTicket,
} from "./api/dataanalyzer";
import FeedbackModal from "./components/FeedbackModal";
import Sidebar from "./components/Sidebar";
import Workspace from "./components/Workspace";
import { writtenDate } from "./components/writtenDate";
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
import { servicesForRoles, SESSION_MODE } from "./services";

/**
 * Origins an embedded application may be served from when they are not
 * configured explicitly. These are the development and shared-hosting
 * addresses of the news frontend, of Peer Benchmarking, of the Data
 * Summarizer and of the SQL Genie.
 */
const DEFAULT_CHILD_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://newsintel.pnbbank.in:5173",
    "http://localhost:8077",
    "http://127.0.0.1:8077",
    "http://newsintel.pnbbank.in:8077",
    "http://localhost:8090",
    "http://127.0.0.1:8090",
    "http://newsintel.pnbbank.in:8090",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:8095",
    "http://127.0.0.1:8095",
];

/**
 * The services that keep their own sessions.
 *
 * For each of them the hub asks for two things when the service is opened: the
 * list of screens, and a single-use sign-in ticket for the person who signed in
 * here. The ticket is spent once, so a new one is asked for every time.
 */
const TICKET_SERVICES = {
    benchmark: {
        label: "Peer Benchmarking",
        manifest: fetchBenchmarkManifest,
        ticket: requestBenchmarkTicket,
    },
    summarizer: {
        label: "Data Summarizer",
        manifest: fetchSummarizerManifest,
        ticket: requestSummarizerTicket,
    },
    analyzer: {
        label: "Data Analyzer",
        manifest: fetchAnalyzerManifest,
        ticket: requestAnalyzerTicket,
    },
};

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

    // The single-use sign-in ticket of each service that keeps its own
    // sessions, keyed by the service. A ticket is spent once, so a new one is
    // asked for every time the service is opened.
    const [tickets, setTickets] = useState({});

    const [isCollapsed, setIsCollapsed] = useState(() =>
        readSidebarCollapsed(window.localStorage),
    );

    const clearSession = useCallback(() => {
        clearHubSession(window.localStorage);

        setSession(null);
        setAuthStatus("anonymous");
        setActiveServiceId(null);
        setPendingLogout(false);
        setTickets({});
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
                    roleNews: user.role_news,
                    roleBench: user.role_bench,
                    roleNewsLabel: user.role_news_label ?? stored.roleNewsLabel,
                    roleBenchLabel: user.role_bench_label ?? stored.roleBenchLabel,
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

    // Who may open which service is decided by the role the person holds in
    // that service: the News Feed by `role_news`, Peer Benchmarking by
    // `role_bench`.
    const services = useMemo(
        () =>
            session
                ? servicesForRoles({
                      news: session.roleNews,
                      bench: session.roleBench,
                  })
                : [],
        [session],
    );

    const activeService = useMemo(
        () => services.find((service) => service.id === activeServiceId),
        [services, activeServiceId],
    );

    // A service that keeps its own navigation and its own sessions. When it is
    // opened, the hub asks it for the list of screens and for a single-use
    // sign-in ticket for the person who signed in here.
    useEffect(() => {
        const service = TICKET_SERVICES[activeService?.id];

        if (!service) {
            return undefined;
        }

        let cancelled = false;

        const open = async () => {
            try {
                const manifest = await service.manifest();

                if (cancelled) {
                    return;
                }

                setSections((previous) => ({
                    ...previous,
                    [activeService.id]: manifest.sections ?? [],
                }));

                setActiveSectionId(manifest.defaultSection ?? "overview");

                const ticket = await service.ticket();

                if (cancelled) {
                    return;
                }

                setTickets((previous) => ({
                    ...previous,
                    [activeService.id]: {
                        ticket: ticket.ticket,
                        role: ticket.role,
                        notice: "",
                    },
                }));
            } catch (err) {
                if (cancelled) {
                    return;
                }

                console.error(`${service.label} could not be opened:`, err);

                setTickets((previous) => ({
                    ...previous,
                    [activeService.id]: {
                        ticket: null,
                        role: null,
                        notice:
                            err.response?.data?.detail ??
                            `${service.label} is not available right now.`,
                    },
                }));
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
            const ticket = tickets[activeService.id];

            if (!ticket?.ticket) {
                return null;
            }

            // Peer Benchmarking keeps its own sessions and decides what
            // the benchmarking role may do there, so it is given that role.
            if (activeService.id === "benchmark") {
                return {
                    username: session.username,
                    roleBench: session.roleBench,
                    ticket: ticket.ticket,
                };
            }

            // The Data Summarizer keeps its own accounts and decides the role
            // there itself, so it is given only the ticket.
            return {
                username: session.username,
                role: ticket.role,
                ticket: ticket.ticket,
            };
        }

        // The News Feed shares this platform's token, and decides what the
        // news role may do there.
        if (activeService.id === "news") {
            return {
                username: session.username,
                roleNews: session.roleNews,
                accessToken: session.accessToken,
            };
        }

        // The SQL Genie shares the token as well. It is not told a role: it
        // asks the backend who the person is, and decides for itself what
        // they may do.
        return {
            username: session.username,
            accessToken: session.accessToken,
        };
    }, [session, activeService, tickets]);

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

    // A person holds one role in each application, and the button says which
    // is which.
    const roleLabel = [
        `News Feed: ${session.roleNewsLabel ?? session.roleNews}`,
        `Peer Benchmarking: ${session.roleBenchLabel ?? session.roleBench}`,
    ].join(" · ");

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
                            {writtenDate(new Date())}
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

                        // A ticket is spent once, so it is dropped as soon
                        // as its service is closed.
                        if (nextId !== selected.id) {
                            setTickets((previous) => {
                                const next = { ...previous };

                                delete next[selected.id];

                                return next;
                            });
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
                        notice={tickets[activeService?.id]?.notice ?? ""}
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
