import AppCard from "./AppCard";

function ChevronIcon() {
    return (
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            <path d="M15 18l-6-6 6-6" />
        </svg>
    );
}

function Sidebar({
    services,
    activeServiceId,
    activeSectionId,
    sections,
    isCollapsed,
    onToggle,
    onSelect,
    onSelectSection,
}) {
    return (
        <aside className="sidebar">
            <div className="sidebar-panel">
                <div className="sidebar-head">
                    <div className="sidebar-title">
                        Intelligence Services
                    </div>

                    <button
                        type="button"
                        className="sidebar-toggle"
                        onClick={onToggle}
                        aria-expanded={!isCollapsed}
                        aria-controls="hub-services"
                        title={
                            isCollapsed
                                ? "Expand the service list"
                                : "Collapse the service list"
                        }
                    >
                        <ChevronIcon />

                        <span className="sr-only">
                            {isCollapsed
                                ? "Expand the service list"
                                : "Collapse the service list"}
                        </span>
                    </button>
                </div>

                <div className="app-list" id="hub-services">
                    {services.map((service) => {
                        const serviceSections =
                            service.id === activeServiceId
                                ? sections?.[service.id] ?? []
                                : [];

                        return (
                            <div className="app-group" key={service.id}>
                                <AppCard
                                    service={service}
                                    isActive={service.id === activeServiceId}
                                    isCollapsed={isCollapsed}
                                    onSelect={onSelect}
                                />

                                {serviceSections.length > 0 && (
                                    <div
                                        className="app-sections"
                                        role="group"
                                        aria-label={`${service.name} screens`}
                                    >
                                        {serviceSections.map((section) => (
                                            <button
                                                key={section.id}
                                                type="button"
                                                className={`app-section${
                                                    section.id ===
                                                    activeSectionId
                                                        ? " active"
                                                        : ""
                                                }`}
                                                onClick={() =>
                                                    onSelectSection(section)
                                                }
                                                aria-current={
                                                    section.id ===
                                                    activeSectionId
                                                        ? "page"
                                                        : undefined
                                                }
                                                title={section.title}
                                            >
                                                <span
                                                    className="app-section-marker"
                                                    aria-hidden="true"
                                                />

                                                <span className="app-section-name">
                                                    {section.title}
                                                </span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </aside>
    );
}

export default Sidebar;
