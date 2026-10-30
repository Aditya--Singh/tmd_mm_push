import { useEffect, useRef } from "react";

import { SERVICE_STATUS } from "../services";

/**
 * Add the marker that tells the embedded application to render in its
 * embedded variant.
 */
function withEmbeddedFlag(url) {
    try {
        const parsed = new URL(url, window.location.href);

        parsed.searchParams.set("embedded", "1");

        return parsed.toString();
    } catch {
        return url;
    }
}

function WelcomePanel() {
    return (
        <>
            <h2>Welcome to Executive Intelligence Hub</h2>

            <p>
                This platform brings together multiple AI-powered
                intelligence services into a unified experience designed to
                assist executives in data-driven decision making.
            </p>

            <div className="capabilities">
                <h3>Platform Capabilities</h3>

                <ul>
                    <li>
                        Query enterprise databases using natural language
                        through conversational AI.
                    </li>

                    <li>
                        Generate concise executive summaries from PDF,
                        PowerPoint and Excel documents.
                    </li>

                    <li>
                        Compare organizational performance against banking
                        peers using benchmarking dashboards.
                    </li>

                    <li>
                        Monitor business, economic and regulatory
                        developments through curated news intelligence.
                    </li>

                    <li>
                        Reduce manual effort through AI-assisted analysis and
                        summarization.
                    </li>

                    <li>
                        Access multiple intelligence services through a single
                        integrated platform.
                    </li>

                    <li>
                        Maintain a consistent user experience across all
                        applications.
                    </li>

                    <li>
                        Support strategic and tactical decision making with
                        AI-generated insights.
                    </li>
                </ul>
            </div>
        </>
    );
}

function PlannedPanel({ service }) {
    return (
        <div className="placeholder">
            <div className="placeholder-title">
                {service.icon} {service.name}
            </div>

            <p>
                This service is part of the platform scope and is being
                prepared. It will open here in the workspace once it is
                available.
            </p>
        </div>
    );
}

function Workspace({ bridge, service, session }) {
    const frameRef = useRef(null);

    const isLive = service?.status === SERVICE_STATUS.LIVE;

    const frameSrc = isLive ? withEmbeddedFlag(service.url) : null;

    // Register the frame as soon as it is mounted, not once it has
    // loaded. A message that is sent to a frame that is still loading is
    // queued by the browser, whereas a message that is sent to the wrong
    // frame is lost.
    const registerFrame = (element) => {
        frameRef.current = element;
        bridge.setFrameElement(element);
    };

    // Hand the session over as soon as the frame has loaded. The bridge
    // also answers the "ready" message the frame sends on start-up, so
    // the session is delivered either way.
    const handleFrameLoad = () => {
        if (!isLive) {
            return;
        }

        bridge.sendSession();
    };

    useEffect(() => {
        if (!isLive) {
            bridge.setFrameElement(null);
        }
    }, [isLive, bridge]);

    // A session change must reach the frame as well, so that a re-login
    // is picked up without a reload.
    useEffect(() => {
        if (isLive) {
            bridge.sendSession();
        }
    }, [bridge, isLive, session]);

    return (
        <section id="workspace" className="workspace">
            {!service && (
                <div className="workspace-body">
                    <WelcomePanel />
                </div>
            )}

            {service && !isLive && (
                <div className="workspace-body">
                    <h2>{service.name}</h2>

                    <PlannedPanel service={service} />
                </div>
            )}

            {service && isLive && (
                <div className="workspace-frame">
                    <iframe
                        ref={registerFrame}
                        src={frameSrc}
                        title={service.name}
                        onLoad={handleFrameLoad}
                    />
                </div>
            )}
        </section>
    );
}

export default Workspace;
