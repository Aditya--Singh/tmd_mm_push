/**
 * A minimal reverse proxy that reproduces the production layout:
 *
 *   /        -> the landing page (static build)
 *   /news/   -> the news application (static build)
 *   /api/    -> the FastAPI backend
 *
 * It exists so that the same-origin deployment can be exercised without
 * a full web server. Everything is served from one origin, which is the
 * arrangement the platform is expected to run in.
 */

import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";

const HUB_DIST = process.env.HUB_DIST;
const NEWS_DIST = process.env.NEWS_DIST;
const API_TARGET = process.env.API_TARGET || "http://127.0.0.1:8000";
const PORT = Number(process.env.PORT || 5175);

const MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
};

function resolveFile(root, urlPath, { spa = false } = {}) {
    const relative = normalize(decodeURIComponent(urlPath)).replace(/^(\.\.[/\\])+/, "");

    let filePath = join(root, relative);

    if (existsSync(filePath) && statSync(filePath).isDirectory()) {
        filePath = join(filePath, "index.html");
    }

    if (!existsSync(filePath) && spa) {
        filePath = join(root, "index.html");
    }

    return existsSync(filePath) ? filePath : null;
}

function serveFile(response, filePath) {
    response.writeHead(200, {
        "Content-Type": MIME[extname(filePath)] || "application/octet-stream",
    });

    createReadStream(filePath).pipe(response);
}

function proxyApi(request, response) {
    const upstream = httpRequest(
        `${API_TARGET}${request.url}`,
        {
            method: request.method,
            headers: { ...request.headers, host: "127.0.0.1:8000" },
        },
        (upstreamResponse) => {
            response.writeHead(upstreamResponse.statusCode, upstreamResponse.headers);

            upstreamResponse.pipe(response);
        },
    );

    upstream.on("error", (error) => {
        response.writeHead(502);
        response.end(String(error));
    });

    request.pipe(upstream);
}

const server = createServer((request, response) => {
    const urlPath = request.url.split("?")[0];

    if (urlPath.startsWith("/api/")) {
        proxyApi(request, response);
        return;
    }

    if (urlPath.startsWith("/news")) {
        const newsPath = urlPath.replace(/^\/news/, "") || "/";

        const filePath = resolveFile(NEWS_DIST, newsPath, { spa: true });

        if (filePath) {
            serveFile(response, filePath);
            return;
        }
    }

    const hubPath = urlPath === "/" ? "/index.html" : urlPath;

    const filePath = resolveFile(HUB_DIST, hubPath, { spa: true });

    if (filePath) {
        serveFile(response, filePath);
        return;
    }

    response.writeHead(404);
    response.end("not found");
});

server.listen(PORT, "127.0.0.1", () => {
    console.log(`same-origin proxy listening on http://127.0.0.1:${PORT}`);
});
