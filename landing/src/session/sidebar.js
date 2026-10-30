/**
 * The service rail.
 *
 * The rail can be collapsed to an icon column so that the workspace
 * gets the room. The choice is remembered between visits.
 */

const STORAGE_KEY = "bankHubSidebarCollapsed";

export function readSidebarCollapsed(storage) {
    try {
        return storage.getItem(STORAGE_KEY) === "true";
    } catch {
        return false;
    }
}

export function writeSidebarCollapsed(collapsed, storage) {
    try {
        storage.setItem(STORAGE_KEY, collapsed ? "true" : "false");
    } catch {
        // Storage is not always available, the choice is not essential.
    }
}
