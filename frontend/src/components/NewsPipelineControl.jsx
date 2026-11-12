import { useState } from "react";

import { runNewsIngestion } from "../api/admin";
import { cutoffDate, DEFAULT_DAYS, WINDOWS } from "./pipelineWindow";

function NewsPipelineControl() {
    const [days, setDays] = useState(DEFAULT_DAYS);
    const [running, setRunning] = useState(false);
    const [message, setMessage] = useState("");

    const handleRun = async () => {
        setRunning(true);
        setMessage("");

        try {
            const result = await runNewsIngestion(days);

            setMessage(
                result.message ||
                "News ingestion started successfully.",
            );
        } catch (error) {
            console.error(
                "Unable to start news ingestion:",
                error,
            );

            setMessage(
                "Unable to start news ingestion.",
            );
        } finally {
            setRunning(false);
        }
    };

    return (
        <section className="panel news-pipeline-panel">
            <div className="section-header">
                <div>
                    <h2>News Data Pipeline</h2>
                    <p>
                        Fetch latest news and run AI analysis
                    </p>
                </div>
            </div>

            <div className="pipeline-controls">
                <label
                    className="pipeline-window"
                    htmlFor="pipeline-window"
                >
                    <span>Store news from</span>

                    <select
                        id="pipeline-window"
                        value={days}
                        onChange={(event) =>
                            setDays(Number(event.target.value))
                        }
                        disabled={running}
                    >
                        {WINDOWS.map((window) => (
                            <option
                                key={window.days}
                                value={window.days}
                            >
                                {window.label}
                            </option>
                        ))}
                    </select>
                </label>

                <button
                    type="button"
                    className="pipeline-button"
                    onClick={handleRun}
                    disabled={running}
                >
                    {running
                        ? "Starting..."
                        : "Run News Ingestion"}
                </button>
            </div>

            <p className="pipeline-note">
                News published from {cutoffDate(days)} will be
                stored. Anything older is left out.
            </p>

            {message && (
                <p className="pipeline-message">
                    {message}
                </p>
            )}
        </section>
    );
}

export default NewsPipelineControl;
