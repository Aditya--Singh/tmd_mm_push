#!/usr/bin/env python3
"""
Health check for PNB Regulatory Sentinel. Works on the GB10 (Linux) and on Windows; needs only Python 3.

    python3 scripts/check.py              (GB10 / Linux)
    py scripts\\check.py                  (Windows)
    python3 scripts/check.py --url http://10.20.30.40:8090     (check an app on another machine)

Each line says OK, WARN or FIX. Every FIX line says what to do. Nothing is changed by this script.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USE_COLOUR = sys.stdout.isatty() and (os.name != "nt" or bool(os.environ.get("WT_SESSION")))
COUNTS = {"OK": 0, "WARN": 0, "FIX": 0}


def say(level: str, what: str, detail: str = "", fix: str = "") -> None:
    COUNTS[level] += 1
    colour = {"OK": "\033[32m", "WARN": "\033[33m", "FIX": "\033[31m"}[level] if USE_COLOUR else ""
    reset = "\033[0m" if USE_COLOUR else ""
    print(f"{colour}[{level:<4}]{reset} {what}" + (f" - {detail}" if detail else ""))
    if fix and level != "OK":
        for line in fix.splitlines():
            print(f"         -> {line}")


def section(title: str) -> None:
    print(f"\n== {title} " + "=" * max(0, 60 - len(title)))


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return env


def get_json(url: str, timeout: float = 10, method: str = "GET") -> object:
    req = urllib.request.Request(url, method=method, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def run(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "not installed"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


# --------------------------------------------------------------------------- checks
def check_settings(env: dict[str, str]) -> None:
    section("Settings file")
    if not env:
        say("FIX", ".env file", "missing", "Copy the example: cp .env.example .env   (Windows: Copy-Item .env.example .env)")
        return
    say("OK", ".env file", "found")
    for k in ("AUTH_ENABLED", "EMAIL_ENABLED"):
        say("OK", k, env.get(k, "false (default)"))


def check_gpu() -> None:
    section("GPU")
    if not shutil.which("nvidia-smi"):
        say("WARN", "nvidia-smi", "not found", "Fine on a laptop without an NVIDIA GPU (Ollama then runs on the CPU, slower).\n"
            "On the GB10 it should exist: reboot once, then run nvidia-smi again.")
        return
    code, out = run(["nvidia-smi", "--query-gpu=name,driver_version,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                     "--format=csv,noheader,nounits"])
    if code != 0:
        say("FIX", "nvidia-smi", out.strip()[:200] or f"exit code {code}",
            "The GPU driver is not answering. Reboot the machine. If it persists: sudo apt install --reinstall nvidia-driver (ask IT).")
        return
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        name, driver, temp, util = (parts + ["?"] * 4)[:4]
        mem = f"{parts[4]} / {parts[5]} MiB" if len(parts) > 5 and parts[5] not in ("[N/A]", "N/A") else "unified memory"
        detail = f"{name}, driver {driver}, {temp} C, {util}% busy, memory {mem}"
        try:
            hot = float(temp) >= 85
        except ValueError:
            hot = False
        say("WARN" if hot else "OK", "GPU", detail,
            "Running hot. Check the vents are clear and the room is cool; it may have shut down for this reason." if hot else "")


def check_disk() -> None:
    section("Disk")
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < 5:
        say("FIX", "Free disk space", f"{free_gb:.1f} GB", "Free some space: docker system prune  (removes old build layers; your data volume is kept)")
    elif free_gb < 15:
        say("WARN", "Free disk space", f"{free_gb:.1f} GB", "Getting low. docker system prune frees old build layers.")
    else:
        say("OK", "Free disk space", f"{free_gb:.0f} GB")


def ollama_root(env: dict[str, str], override: str | None) -> str:
    base = override or env.get("OLLAMA_URL") or env.get("LLM_BASE_URL") or "http://localhost:11434/v1"
    base = base.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def check_ollama(env: dict[str, str], override: str | None) -> None:
    section("Ollama (the AI models)")
    if env.get("LLM_PROVIDER", "openai_compat") != "openai_compat":
        say("OK", "LLM provider", env.get("LLM_PROVIDER", ""), "")
        return
    root = ollama_root(env, override)
    try:
        tags = get_json(f"{root}/api/tags", timeout=8)
    except Exception as e:  # noqa: BLE001
        say("FIX", f"Ollama at {root}", f"not answering ({e.__class__.__name__})",
            "GB10:    sudo systemctl start ollama   then   systemctl status ollama\n"
            "Windows: start 'Ollama' from the Start menu (it sits in the tray by the clock)\n"
            "If the models are on another machine, set OLLAMA_URL / LLM_BASE_URL in .env to that machine.")
        return
    names = {m.get("name", "") for m in tags.get("models", [])}
    say("OK", f"Ollama at {root}", f"{len(names)} models installed")
    for key, default in (("LLM_MODEL", "gpt-oss:20b"), ("EMBEDDING_MODEL", "bge-m3")):
        want = env.get(key, default)
        if key == "EMBEDDING_MODEL" and env.get("EMBEDDING_PROVIDER", "openai_compat") != "openai_compat":
            continue
        have = want in names or f"{want}:latest" in names or any(n.split(":")[0] == want for n in names)
        say("OK" if have else "FIX", f"Model {want}", "installed" if have else "missing", f"ollama pull {want}")
    try:
        ps = get_json(f"{root}/api/ps", timeout=8)
        for m in ps.get("models", []):
            size, vram = m.get("size") or 0, m.get("size_vram") or 0
            where = "GPU" if size and vram >= size * 0.95 else ("CPU" if not vram else f"{round(100 * vram / size)}% GPU")
            say("OK" if where == "GPU" else "WARN", f"Loaded now: {m.get('name')}", f"running on {where}",
                "" if where == "GPU" else "Ollama is not using the GPU fully. Restart it: sudo systemctl restart ollama, then check nvidia-smi.")
        if not ps.get("models"):
            say("OK", "Loaded now", "no model loaded (normal when idle; the first question loads it, ~30 s)")
    except Exception:  # noqa: BLE001
        pass


def check_docker(no_docker: bool) -> None:
    section("Docker container")
    if no_docker:
        say("OK", "Docker", "skipped (--no-docker)")
        return
    if not shutil.which("docker"):
        say("WARN", "Docker", "not installed here", "Fine if you run the app without Docker (run.sh / run.ps1). Otherwise install Docker.")
        return
    code, out = run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if code != 0:
        say("FIX", "Docker engine", "not running",
            "GB10:    sudo systemctl start docker\nWindows: open Docker Desktop and wait until it says 'Engine running'")
        return
    say("OK", "Docker engine", f"version {out.strip()}")
    code, out = run(["docker", "inspect", "--format", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.RestartCount}}", "pnb-sentinel"])
    if code != 0:
        say("FIX", "Container pnb-sentinel", "does not exist",
            "Build and start it from the project folder:\n"
            "GB10:    docker compose up -d --build\n"
            "Windows: docker compose -f docker-compose.windows.yml up -d --build")
        return
    status, health, restarts = (out.split() + ["", "", "0"])[:3]
    if status != "running":
        say("FIX", "Container pnb-sentinel", status,
            "Start it: docker compose up -d   (Windows: docker compose -f docker-compose.windows.yml up -d)\n"
            "If it stops again, read why: docker compose logs --tail 80 sentinel")
    elif health == "unhealthy":
        say("FIX", "Container pnb-sentinel", "running but unhealthy", "docker compose logs --tail 80 sentinel   then   docker compose restart")
    else:
        say("OK", "Container pnb-sentinel", f"{status} {health or ''}".strip() + (f", restarted {restarts}x" if restarts not in ("0", "") else ""))


def check_app(url: str) -> None:
    section(f"App at {url}")
    try:
        h = get_json(f"{url}/api/health", timeout=10)
    except Exception as e:  # noqa: BLE001
        say("FIX", "App", f"not answering ({e.__class__.__name__})",
            "Wait a minute after starting (it loads models first), then run this check again.\n"
            "Still failing: docker compose logs --tail 80 sentinel   (or read the run.ps1 / run.sh window)")
        return
    say("OK", "App", f"answering, {h.get('index_chunks', 0)} search chunks")
    try:
        d = get_json(f"{url}/api/dashboard", timeout=30)
    except urllib.error.HTTPError as e:
        say("WARN", "Dashboard", f"HTTP {e.code}", "Login is switched on; open the app in the browser to check the rest.")
        return
    except Exception as e:  # noqa: BLE001
        say("WARN", "Dashboard", e.__class__.__name__)
        return

    sysinfo = d.get("system", {})
    emb, fb = sysinfo.get("embedding_model"), sysinfo.get("embedding_fallback")
    say("FIX" if fb else "OK", "Search model (embeddings)", f"{emb}" + (f" - fell back: {fb}" if fb else ""),
        "The app started before Ollama was ready. Make sure Ollama answers (see above), then:\n"
        "docker compose restart   (Windows: docker compose -f docker-compose.windows.yml restart)")
    llm = sysinfo.get("llm", {})
    if llm.get("provider") == "none":
        say("OK", "Language model", "switched off (LLM_PROVIDER=none)")
    else:
        try:
            llm = get_json(f"{url}/api/system/llm-check", timeout=180, method="POST")
        except Exception:  # noqa: BLE001
            pass
        ok = llm.get("healthy")
        say("OK" if ok else ("WARN" if ok is None else "FIX"), "Language model", f"{llm.get('model')} healthy={ok}"
            + (f" - {llm.get('last_error')}" if llm.get("last_error") else ""),
            "Check Ollama above. Then open Settings in the app and click 'Check model'.")

    sync = d.get("sync", {})
    last = sync.get("last_result") or {}
    if sync.get("running"):
        say("OK", "RBI sync", "running now")
    elif last:
        waiting = last.get("deferred", 0)
        say("OK", "RBI sync", f"last finished {sync.get('last_finished', '?')[:19]} UTC"
            + (f", {waiting} documents still to read (continues by itself)" if waiting else ", all caught up"))
    else:
        say("WARN", "RBI sync", "has not run yet", "It starts ~10 s after the app starts. Or click 'Check RBI now' on Overview.")

    for c in d.get("coverage", []):
        src, ok, n = c.get("source"), c.get("last_ok"), c.get("indexed", 0)
        if ok is False:
            say("FIX", f"Source {src}", f"last read failed: {(c.get('last_error') or '')[:120]}",
                "Check this machine can open https://www.rbi.org.in in a browser. The app retries every 30 minutes.")
        elif ok is None:
            say("WARN", f"Source {src}", f"{n} indexed, not read since the app started (normal in the first minutes)")
        else:
            extra = f", {c.get('waiting')} waiting" if c.get("waiting") else ""
            say("OK", f"Source {src}", f"{n} indexed, last read {c.get('last_entries')} entries{extra}")

    k = d.get("kpis", {})
    current = max(0, (k.get("indexed") or 0) - (k.get("superseded") or 0))
    done = k.get("ai_summarised") or 0
    say("OK", "AI summaries", f"{done} written; {current} current documents (a few more every 5 minutes)")


def main() -> int:
    env = read_env()
    p = argparse.ArgumentParser(description="Health check for PNB Regulatory Sentinel")
    p.add_argument("--url", default=f"http://localhost:{env.get('PORT', '8090')}", help="address of the app")
    p.add_argument("--ollama", default=None, help="address of Ollama, e.g. http://10.20.30.40:11434")
    p.add_argument("--no-docker", action="store_true", help="skip the Docker checks (app runs with run.sh / run.ps1)")
    a = p.parse_args()

    print("PNB Regulatory Sentinel - health check")
    check_settings(env)
    check_gpu()
    check_disk()
    check_ollama(env, a.ollama)
    check_docker(a.no_docker)
    check_app(a.url.rstrip("/"))

    print(f"\nResult: {COUNTS['OK']} OK, {COUNTS['WARN']} WARN, {COUNTS['FIX']} FIX")
    print("All good." if not COUNTS["FIX"] else "Do the '->' steps for each FIX line, then run this check again.")
    return 1 if COUNTS["FIX"] else 0


if __name__ == "__main__":
    sys.exit(main())
