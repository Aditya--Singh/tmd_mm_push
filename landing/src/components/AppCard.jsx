import { SERVICE_STATUS } from "../services";

function AppCard({ service, isActive, isCollapsed, onSelect }) {
    const isPlanned = service.status === SERVICE_STATUS.PLANNED;

    return (
        <div
            className={`app-card${isActive ? " active" : ""}`}
            role="button"
            tabIndex={0}
            aria-pressed={isActive}
            title={isCollapsed ? service.name : undefined}
            onClick={() => onSelect(service)}
            onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(service);
                }
            }}
        >
            <div className="app-top">
                <div className="icon" aria-hidden="true">
                    {service.icon}
                </div>

                <div className="app-name">{service.name}</div>

                {isPlanned && <div className="app-badge">Planned</div>}
            </div>

            <div className="app-desc">{service.description}</div>
        </div>
    );
}

export default AppCard;
