/**
 * The session of this app.
 *
 * The app keeps no accounts of its own: the hub signs the person in and hands over a
 * single-use ticket, which is swapped for a token of this app. The token is the only
 * thing the API calls carry.
 */
import { getHubClient } from "./hub";

let token = "";

export function setToken(value: string) {
  token = value;
}

export function getToken(): string {
  return token;
}

export function forgetToken() {
  token = "";
}

/** The headers every call to this app's own API carries. */
export function authHeaders(): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Confirm to the hub that this app has signed the person out. */
export function acknowledgeLogout() {
  getHubClient()?.acknowledgeLogout();
}
