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
    isCollapsed,
    onToggle,
    onSelect,
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
                    {services.map((service) => (
                        <AppCard
                            key={service.id}
                            service={service}
                            isActive={service.id === activeServiceId}
                            isCollapsed={isCollapsed}
                            onSelect={onSelect}
                        />
                    ))}
                </div>
            </div>
        </aside>
    );
}

export default Sidebar;
