import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    askAbout,
    exchangeTicket,
    getDocument,
    listDocuments,
    makeInsights,
    makeSummary,
    meta,
    plotUrl,
    readToken,
    removeDocument,
    uploadDocument,
    writeToken,
} from "./lib/api.js";
import { acknowledgeLogout, installBridge } from "./lib/hub.js";
import { isEmbed } from "./lib/embed.js";

/**
 * The origins that may drive this application.
 *
 * The server knows them, because they are its own settings. They are asked for before
 * the bridge is put in place, so that a message from a page that may not drive this
 * application is never listened to.
 */
async function the_origins_that_may_drive_us() {
    try {
        const answer = await meta();

        return answer?.embed_parent_origins ?? [];
    } catch {
        return [];
    }
}

/**
 * The Data Analyzer.
 *
 * The hub owns the sign-in: it hands this app a single-use ticket over the bridge, and
 * this app swaps that ticket for a session of its own. The role is the role the person
 * holds in the News Feed of the platform.
 */
function App() {
    const [status, setStatus] = useState("signing-in");
    const [person, setPerson] = useState(null);
    const [error, setError] = useState("");
    const [documents, setDocuments] = useState([]);
    const [activeId, setActiveId] = useState(null);
    const [document, setDocument] = useState(null);
    const [busy, setBusy] = useState(false);
    const [notice, setNotice] = useState("");
    const [model, setModel] = useState(null);

    const embedded = useMemo(() => isEmbed(), []);

    // The ticket that was already spent. A ticket can be used once only, and the
    // bridge may hand the same one over twice: it answers the "ready" message of
    // the frame and the hub may push the session as well.
    const spentTicket = useRef("");

    // The hub asks for a ticket and hands it over. The ticket is spent once.
    useEffect(() => {
        let cancelled = false;

        const signIn = async (payload) => {
            if (cancelled || !payload?.ticket) {
                return;
            }

            // The same ticket twice is not a second sign-in.
            if (spentTicket.current === payload.ticket) {
                return;
            }

            spentTicket.current = payload.ticket;

            try {
                const answer = await exchangeTicket(payload.ticket);

                writeToken(answer.access_token);
                setPerson(answer.user);
                setStatus("signed-in");
            } catch (exc) {
                if (cancelled) {
                    return;
                }

                // The ticket may have been spent by the first attempt, and the
                // session may be there already.
                if (readToken()) {
                    setStatus("signed-in");

                    return;
                }

                setError(exc.message || "The sign-in could not be completed.");
                setStatus("refused");
            }
        };

        const start = async () => {
            const origins = await the_origins_that_may_drive_us();

            if (cancelled) {
                return;
            }

            const bridge = installBridge({
                allowedParentOrigins: origins,
                onAuth: signIn,
                onLogout: () => {
                    writeToken("");
                    setPerson(null);
                    setStatus("signed-out");

                    // The hub waits for this answer before it takes the frame
                    // away, so that a message that is still on its way is not lost.
                    acknowledgeLogout();
                },
            });

            // The hub may have answered before this app was ready to listen.
            if (readToken()) {
                setStatus("signed-in");
            } else {
                bridge.requestSession();
            }
        };

        void start();

        return () => {
            cancelled = true;
        };
    }, []);

    // The list of documents, once the person is signed in.
    const refresh = useCallback(async () => {
        try {
            const answer = await listDocuments();
            setDocuments(answer.documents || []);
            setPerson((previous) =>
                previous ? { ...previous, role: answer.role || previous.role } : previous,
            );
        } catch (exc) {
            setError(exc.message);
        }
    }, []);

    useEffect(() => {
        if (status !== "signed-in") {
            return;
        }

        refresh();
        meta().then((answer) => setModel(answer.model)).catch(() => {});
    }, [status, refresh]);

    const open = useCallback(async (id) => {
        setActiveId(id);
        setDocument(null);

        try {
            setDocument(await getDocument(id));
        } catch (exc) {
            setError(exc.message);
        }
    }, []);

    const share = useCallback(
        async (file) => {
            setBusy(true);
            setError("");
            setNotice("");

            try {
                const answer = await uploadDocument(file);

                setNotice(`${answer.name} was read: ${answer.rows} rows, ${answer.columns} columns.`);

                await refresh();
                await open(answer.id);
            } catch (exc) {
                setError(exc.message || "The document could not be read.");
            } finally {
                setBusy(false);
            }
        },
        [refresh, open],
    );

    const remove = useCallback(
        async (id) => {
            setBusy(true);

            try {
                await removeDocument(id);
                setActiveId(null);
                setDocument(null);
                await refresh();
            } catch (exc) {
                setError(exc.message);
            } finally {
                setBusy(false);
            }
        },
        [refresh],
    );

    const ask = useCallback(
        async (question) => {
            if (!activeId) {
                return;
            }

            setBusy(true);

            try {
                const answer = await askAbout(activeId, question);
                setDocument((previous) =>
                    previous ? { ...previous, answer: answer.answer } : previous,
                );
            } catch (exc) {
                setError(exc.message);
            } finally {
                setBusy(false);
            }
        },
        [activeId],
    );

    if (status === "signed-in" && !person) {
        // The token of an earlier visit is still there; the list of documents says who.
        return null;
    }

    if (status !== "signed-in") {
        return (
            <div className="waiting">
                <div className="stack" style={{ alignItems: "center" }}>
                    <h1 style={{ fontSize: 18, fontWeight: 600 }}>
                        {status === "refused" ? "The sign-in was refused" : "Signing in…"}
                    </h1>
                    <p className="muted small" style={{ maxWidth: 460 }}>
                        {error ||
                            "This service is opened from the Executive Intelligence Hub. Sign in there, and this page will follow."}
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="shell">
            {/* The hub owns the chrome, so the header is only drawn when this
                application is opened on its own. */}
            {embedded ? null : (
                <header className="topbar">
                    <div className="topbar__mark">A</div>
                    <div>
                        <div className="topbar__title">PNB Data Analyzer</div>
                        <div className="topbar__subtitle">
                            Excel and CSV, read and analysed
                        </div>
                    </div>
                    <div className="topbar__who">
                        {model?.model ? (
                            <span title={model.model_reason || ""}>{model.model}</span>
                        ) : null}
                        <span>
                            {person?.username} · {person?.role_label || person?.role}
                        </span>
                        <span className="avatar">
                            {(person?.username || "?").slice(0, 1).toUpperCase()}
                        </span>
                    </div>
                </header>
            )}

            <main className="content">
                {error ? (
                    <div className="notice notice--error" style={{ marginBottom: 18 }}>
                        {error}
                    </div>
                ) : null}
                {notice ? (
                    <div className="notice notice--info" style={{ marginBottom: 18 }}>
                        {notice}
                    </div>
                ) : null}

                <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
                    <section className="card">
                        <div className="card__head">
                            <span className="card__title">Share a document</span>
                            <span className="muted small">Excel (.xlsx) or CSV</span>
                        </div>
                        <div className="card__body">
                            <label className="dropzone">
                                <input
                                    type="file"
                                    accept=".csv,.tsv,.txt,.xlsx,.xlsm"
                                    style={{ display: "none" }}
                                    onChange={(event) => {
                                        const file = event.target.files?.[0];

                                        if (file) {
                                            share(file);
                                        }

                                        event.target.value = "";
                                    }}
                                />
                                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                                    Choose a file to read
                                </div>
                                <div className="muted small">
                                    {busy ? "Reading…" : "The file stays on this machine."}
                                </div>
                            </label>
                        </div>
                    </section>

                    <section className="card">
                        <div className="card__head">
                            <span className="card__title">Documents</span>
                            <span className="muted small">{documents.length} shared</span>
                        </div>
                        {documents.length === 0 ? (
                            <div className="card__body muted small">
                                No document has been shared yet.
                            </div>
                        ) : (
                            <ul className="list">
                                {documents.map((item) => (
                                    <li
                                        key={item.id}
                                        className={`list__row ${item.id === activeId ? "list__row--active" : ""}`}
                                        onClick={() => open(item.id)}
                                    >
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontWeight: 600 }}>{item.name}</div>
                                            <div className="muted small">
                                                {item.rows} rows · {item.columns} columns ·{" "}
                                                {item.uploadedBy}
                                            </div>
                                        </div>
                                        {item.hasSummary ? (
                                            <span className="pill pill--date">Read</span>
                                        ) : null}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    {document ? (
                        <DocumentView
                            document={document}
                            busy={busy}
                            person={person}
                            onRemove={() => remove(document.id)}
                            onSummary={async () => {
                                setBusy(true);

                                try {
                                    const answer = await makeSummary(document.id);
                                    setDocument((previous) =>
                                        previous
                                            ? {
                                                  ...previous,
                                                  summary: answer.summary,
                                                  summaryReason: answer.reason,
                                              }
                                            : previous,
                                    );
                                } catch (exc) {
                                    setError(exc.message);
                                } finally {
                                    setBusy(false);
                                }
                            }}
                            onInsights={async () => {
                                setBusy(true);

                                try {
                                    const answer = await makeInsights(document.id);
                                    setDocument((previous) =>
                                        previous
                                            ? { ...previous, insights: answer.insights }
                                            : previous,
                                    );
                                } catch (exc) {
                                    setError(exc.message);
                                } finally {
                                    setBusy(false);
                                }
                            }}
                            onAsk={ask}
                        />
                    ) : null}
                </div>
            </main>
        </div>
    );
}

/**
 * One document: what is in it, what was found in it, and a question about it.
 */
function DocumentView({ document, busy, person, onRemove, onSummary, onInsights, onAsk }) {
    const [question, setQuestion] = useState("");

    const profile = document.profile || {};
    const columns = profile.columnProfiles || [];

    return (
        <div className="stack" style={{ gap: 18 }}>
            <section className="card">
                <div className="card__head">
                    <span className="card__title">{document.name}</span>
                    <span className="muted small">
                        {document.rows} rows · {document.columns} columns ·{" "}
                        {document.filename}
                    </span>
                    <div className="row" style={{ marginLeft: "auto" }}>
                        <button className="button button--quiet" onClick={onSummary} disabled={busy}>
                            Summarise again
                        </button>
                        <button className="button button--quiet" onClick={onInsights} disabled={busy}>
                            Look again
                        </button>
                        {person?.role === "admin" ? (
                            <button
                                className="button button--danger"
                                onClick={onRemove}
                                disabled={busy}
                            >
                                Remove
                            </button>
                        ) : null}
                    </div>
                </div>

                <div className="card__body stack">
                    {document.summary ? (
                        <div>
                            <div
                                style={{
                                    fontWeight: 600,
                                    marginBottom: 6,
                                }}
                            >
                                Summary
                            </div>
                            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
                                {document.summary}
                            </p>
                            {document.summaryReason ? (
                                <p className="muted small" style={{ marginBottom: 0 }}>
                                    {document.summaryReason}
                                </p>
                            ) : null}
                        </div>
                    ) : null}
                </div>
            </section>

            {document.insights?.length ? (
                <section className="card">
                    <div className="card__head">
                        <span className="card__title">What was found</span>
                        <span className="muted small">{document.insights.length} findings</span>
                    </div>
                    <div className="card__body stack">
                        {document.insights.map((finding, index) => (
                            <div key={`${finding.title}-${index}`} className={`finding finding--${finding.kind || "insight"}`}>
                                <div className="finding__title">{finding.title}</div>
                                <div className="finding__text">{finding.text}</div>
                            </div>
                        ))}
                    </div>
                </section>
            ) : null}

            {document.plots?.length ? (
                <section className="card">
                    <div className="card__head">
                        <span className="card__title">Pictures</span>
                    </div>
                    <div className="card__body grid grid--plots">
                        {document.plots.map((plot) => (
                            <figure key={plot.file} className="plot" style={{ margin: 0 }}>
                                <img
                                    src={plotUrl(document.id, plot.file)}
                                    alt={`${plot.kind} of ${plot.name}`}
                                />
                                <figcaption className="plot__name">{plot.name}</figcaption>
                            </figure>
                        ))}
                    </div>
                </section>
            ) : null}

            <section className="card">
                <div className="card__head">
                    <span className="card__title">Ask about this document</span>
                </div>
                <div className="card__body stack">
                    <textarea
                        className="textarea"
                        placeholder="Which branch has the highest balance?"
                        value={question}
                        onChange={(event) => setQuestion(event.target.value)}
                    />
                    <div className="row">
                        <button
                            className="button"
                            disabled={busy || !question.trim()}
                            onClick={() => {
                                onAsk(question.trim());
                                setQuestion("");
                            }}
                        >
                            Ask
                        </button>
                    </div>
                    {document.answer ? (
                        <div
                            style={{
                                whiteSpace: "pre-wrap",
                                color: "var(--text-secondary)",
                            }}
                        >
                            {document.answer}
                        </div>
                    ) : null}
                </div>
            </section>

            <section className="card">
                <div className="card__head">
                    <span className="card__title">The columns</span>
                </div>
                <div className="card__body stack">
                    <div className="table__scroll">
                        <table className="table">
                            <thead>
                                <tr>
                                    <th>Column</th>
                                    <th>Kind</th>
                                    <th>Missing</th>
                                    <th>Different</th>
                                    <th>Average</th>
                                    <th>Middle</th>
                                    <th>Smallest</th>
                                    <th>Largest</th>
                                </tr>
                            </thead>
                            <tbody>
                                {columns.map((column) => (
                                    <tr key={column.name}>
                                        <td style={{ fontWeight: 600 }}>{column.name}</td>
                                        <td>
                                            <span
                                                className={`pill pill--${
                                                    column.kind === "number"
                                                        ? "number"
                                                        : column.kind === "date"
                                                          ? "date"
                                                          : "text"
                                                }`}
                                            >
                                                {column.kind}
                                            </span>
                                        </td>
                                        <td>{column.missingPct}%</td>
                                        <td>{column.unique}</td>
                                        <td>{column.mean ?? "—"}</td>
                                        <td>{column.median ?? "—"}</td>
                                        <td>{column.min ?? "—"}</td>
                                        <td>{column.max ?? "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            {document.preview?.length ? (
                <section className="card">
                    <div className="card__head">
                        <span className="card__title">The first rows</span>
                    </div>
                    <div className="card__body">
                        <div className="table__scroll">
                            <table className="table">
                                <thead>
                                    <tr>
                                        {columns.map((column) => (
                                            <th key={column.name}>{column.name}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {document.preview.map((row, index) => (
                                        <tr key={index}>
                                            {columns.map((column) => (
                                                <td key={column.name}>
                                                    {row[column.name] === null ||
                                                    row[column.name] === undefined
                                                        ? "—"
                                                        : String(row[column.name])}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            ) : null}
        </div>
    );
}

export default App;
