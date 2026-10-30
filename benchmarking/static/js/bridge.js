// Frame bridge: the Executive Intelligence Hub embeds this app and signs the user in.
//
// The hub owns authentication. It hands this app a single-use sign-in ticket over the bridge,
// and this app swaps that ticket for a normal session of its own:
//
//   child  -> parent : { type: "hubint:ready" }
//   parent -> child  : { type: "hubint:auth", payload: { username, role, ticket } }
//   parent -> child  : { type: "hubint:navigate", payload: { path } }
//   parent -> child  : { type: "hubint:logout" }
//   child  -> parent : { type: "hubint:logout-ack" }
//
// Only the page that embedded this app may drive it, and only from an origin the server has
// allow-listed (EMBED_PARENT_ORIGINS). Outbound messages always name a specific origin.
import { api, setToken, state } from './util.js';

export const MESSAGE_AUTH = 'hubint:auth';
export const MESSAGE_LOGOUT = 'hubint:logout';
export const MESSAGE_LOGOUT_ACK = 'hubint:logout-ack';
export const MESSAGE_READY = 'hubint:ready';
export const MESSAGE_NAVIGATE = 'hubint:navigate';
export const MESSAGE_ROUTE = 'hubint:route';

function stripTrailingSlash(value) {
  return typeof value === 'string' ? value.replace(/\/+$/, '') : value;
}

export function normaliseOrigins(origins) {
  const list = Array.isArray(origins) ? origins : String(origins ?? '').split(',');
  return list.map((o) => stripTrailingSlash(String(o ?? '').trim())).filter(Boolean);
}

export function isAllowedOrigin(origin, allowedOrigins) {
  if (!origin) return false;
  const candidate = stripTrailingSlash(origin);
  return allowedOrigins.some((a) => stripTrailingSlash(a) === candidate);
}

export function createBridgeClient(options = {}) {
  const {
    win = typeof window !== 'undefined' ? window : undefined,
    allowedParentOrigins = [],
    onAuth = () => {},
    onNavigate = () => {},
    onLogout = () => {},
  } = options;

  const allowedOrigins = normaliseOrigins(allowedParentOrigins);
  let installed = false;

  function isEmbedded() {
    if (!win) return false;
    try { return win.self !== win.top; } catch { return true; }
  }

  function parentOrigin() {
    // The referrer is the most accurate answer, but only when the app is served with a referrer
    // policy that allows it; otherwise the allowlist decides.
    try {
      const referrer = win?.document?.referrer;
      if (referrer) {
        const origin = new URL(referrer).origin;
        if (isAllowedOrigin(origin, allowedOrigins)) return origin;
      }
    } catch { /* malformed or unavailable referrer */ }
    return allowedOrigins[0] || null;
  }

  function isTrustedEvent(event) {
    if (!event || !isEmbedded()) return false;
    if (event.source !== win.parent) return false;
    return isAllowedOrigin(event.origin, allowedOrigins);
  }

  function postToParent(message) {
    if (!isEmbedded()) return false;
    const target = parentOrigin();
    if (!target) return false;
    try {
      win.parent.postMessage(message, target);
      return true;
    } catch {
      return false;
    }
  }

  function handleMessage(event) {
    if (!isTrustedEvent(event)) return;
    const data = event.data;
    if (!data || typeof data !== 'object') return;

    if (data.type === MESSAGE_AUTH) {
      onAuth(data.payload || {});
    } else if (data.type === MESSAGE_NAVIGATE) {
      onNavigate(data.payload || {});
    } else if (data.type === MESSAGE_LOGOUT) {
      onLogout();
    }
  }

  function install() {
    if (installed || !win) return;
    installed = true;
    win.addEventListener('message', handleMessage);
    // Announce readiness only once the listener is in place, so that the answer cannot be missed.
    postToParent({ type: MESSAGE_READY });
  }

  function uninstall() {
    if (!installed || !win) return;
    installed = false;
    win.removeEventListener('message', handleMessage);
  }

  return {
    allowedOrigins,
    install,
    uninstall,
    postToParent,
    requestSession() { return postToParent({ type: MESSAGE_READY }); },
    acknowledgeLogout() { return postToParent({ type: MESSAGE_LOGOUT_ACK }); },
    /** Tell the hub which screen is now on show. */
    reportRoute(path) { return postToParent({ type: MESSAGE_ROUTE, payload: { path } }); },
  };
}

/**
 * Swap a sign-in ticket for a session of this app.
 *
 * The ticket is single use and short lived. When it is spent the browser is asked for a new one.
 */
export async function exchangeTicket(ticket) {
  const r = await api('/api/auth/exchange', { json: { ticket }, noAuthRedirect: true });
  setToken(r.token);
  state.user = r.user;
  return r.user;
}
