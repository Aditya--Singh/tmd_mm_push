# Adding Regulatory Sentinel as a tab in the Top Management Dashboard

> **It is already done.** This application now lives inside the Executive Intelligence
> Hub as the **Data Summarizer**, under `sentinel/` in
> <https://github.com/Aditya--Singh/top-management-dashboard>. The hub signs the
> person in and hands this application a single-use ticket over the message bridge,
> so that the person keeps one identity across the whole platform. See
> [docs/integration.md](../docs/integration.md) in that repository.
>
> The two ways of adding it are written out below, for a dashboard that is not
> the hub.

Regulatory Sentinel runs as its own service (one Docker container) on the GB10 and is added to the dashboard
in one of two ways. **Option A (iframe) takes about ten minutes** and is recommended for the first release.

Below, `SENTINEL` = the address the service runs on, e.g. `http://10.20.30.40:8090`.

---

## Option A — show the whole app in a tab (iframe)

```html
<iframe
  src="SENTINEL/?embed=1&theme=light"
  title="RBI Regulatory Sentinel"
  style="width:100%; height:calc(100vh - 120px); border:0"
></iframe>
```

- `embed=1` hides the app's left sidebar and shows a slim tab bar (Overview, Assistant, Circulars, Agent traces,
  Feedback, Settings) that fits inside a dashboard tab.
- `theme=light` or `theme=dark` matches the dashboard.
- A direct page also works, e.g. `SENTINEL/circulars?embed=1` or `SENTINEL/assistant?embed=1&circular=123`
  (chat limited to one circular).
- Login is off (`AUTH_ENABLED=false`): the app relies on the dashboard's own sign-in and network controls.
- In `.env`, set `FRAME_ANCESTORS` to the dashboard's address so only the dashboard can frame it:

```
FRAME_ANCESTORS=https://tmd.pnb.bank.in
```

Then run `docker compose up -d`.

**If the dashboard is served over HTTPS**, the browser blocks an `http://` iframe (mixed content). Put Sentinel
behind the same reverse proxy as the dashboard, e.g. nginx:

```nginx
location /sentinel/ {
    proxy_pass http://10.20.30.40:8090/;
    proxy_http_version 1.1;
    proxy_buffering off;            # needed for streamed chat answers and the live activity feed
    proxy_read_timeout 600s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

> The single-page app expects to be served from the root of its host. With a sub-path such as `/sentinel/`,
> build the UI with `base: "/sentinel/"` in `frontend/vite.config.ts`, or give Sentinel its own host name
> (e.g. `sentinel.tmd.pnb.bank.in`), which is simpler.

---

## Option B — call the REST API from the dashboard's own screens

All endpoints return JSON. Interactive documentation: **`SENTINEL/docs`** (Swagger UI).
In `.env`, add the dashboard's address to `CORS_ORIGINS` (comma separated) so browser calls are allowed.

| Purpose | Method and path | Notes |
|---|---|---|
| List circulars | `GET /api/circulars` | Query: `q`, `source` (`notification` · `press_release` · `master_circular` · `master_direction`), `priority`, `applicability`, `financial_year` (e.g. `2025-2026`), `current_only=true`, `revised=true`, `page`, `size` |
| One circular with full text | `GET /api/circulars/{id}` | Includes `summary` (headline, key points, action items, applicability, priority) |
| AI summary of one circular | `POST /api/circulars/{id}/summarize` | Writes or refreshes the AI summary; 10–40 s |
| Chat over all circulars (RAG) | `POST /api/chat/stream` | Body `{"message": "...", "conversation_id": null, "include_older": false}`; reply is Server-Sent Events |
| Chat with one circular | `POST /api/chat/stream` | Same, plus `"circular_id": 123` |
| Headline numbers for a tile | `GET /api/dashboard` | `kpis`, `coverage` per source, `latest` 8 publications, agent health |
| Check RBI now | `POST /api/sync` | Runs in the background; `GET /api/sync/status` for progress |
| Health | `GET /api/health` | For monitoring |

### Reading the chat stream

Each line of the response is `data: {json}`. Event types, in order:

| `type` | Meaning |
|---|---|
| `meta` | `conversation_id` (send it back for follow-up questions) and `trace_id` |
| `step` | An agent started or finished (Memory, Router, Retriever, Answer, Verifier …) |
| `sources` | The passages the answer is based on, numbered `n` = 1, 2, … |
| `token` | Next piece of the answer text (append) |
| `replace` | The whole answer text at once (replaces what you have) |
| `verification` | Grounding check of the answer |
| `done` | Finished; `message_id` for feedback |
| `error` | Something failed; `message` explains |

Minimal browser example:

```js
const res = await fetch(`${SENTINEL}/api/chat/stream`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "What is new from the RBI this week?" }),
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "", answer = "";
for (;;) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  let i;
  while ((i = buffer.indexOf("\n\n")) >= 0) {
    const line = buffer.slice(0, i); buffer = buffer.slice(i + 2);
    if (!line.startsWith("data: ")) continue;
    const ev = JSON.parse(line.slice(6));
    if (ev.type === "token") answer += ev.text;
    if (ev.type === "replace") answer = ev.text;
    if (ev.type === "sources") console.log("sources", ev.items);
  }
  render(answer); // your own UI
}
```

Python example:

```python
import json, requests
with requests.post(f"{SENTINEL}/api/chat/stream", json={"message": "Summarise the latest master direction"}, stream=True) as r:
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev["type"] in ("token", "replace"):
                print(ev["text"], end="", flush=True)
```

---

## Things to agree before go-live

- **Who may open it.** With login off, anyone who can reach port 8090 can use it. Keep the GB10 port reachable
  only from the dashboard server (firewall), or set `AUTH_ENABLED=true`.
- **One instance.** Run one container; the search index and live activity feed live in that process.
- **Data.** Everything is stored in the Docker volume `rbi-sentinel_sentinel-data` (SQLite database, logs).
  Back it up with the command in START_HERE.md.
