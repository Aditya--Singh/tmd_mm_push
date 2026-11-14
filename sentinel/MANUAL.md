# PNB Regulatory Sentinel: operating manual

This manual covers every way to run the app, step by step:

| Part | Use it when |
|---|---|
| [A. Restart the GB10 after a shutdown, and what to check](#a-restart-the-gb10-after-a-shutdown-and-what-to-check) | The GB10 was switched off, crashed or lost power |
| [B. First install on the GB10 (Docker)](#b-first-install-on-the-gb10-docker) | Setting it up on the GB10 for the first time |
| [C. Windows with Docker Desktop (recommended on Windows)](#c-windows-with-docker-desktop-recommended-on-windows) | Running it on a Windows PC or laptop |
| [D. Windows without Docker](#d-windows-without-docker) | Docker Desktop is not allowed on the PC |
| [E. Using the GB10's GPU from a Windows PC](#e-using-the-gb10s-gpu-from-a-windows-pc) | The Windows PC has no strong GPU |
| [F. Everyday commands, backup and restore](#f-everyday-commands-backup-and-restore) | Daily running |
| [G. Updating to new code](#g-updating-to-new-code) | A new version arrives (zip or GitHub) |
| [H. Putting the code on GitHub](#h-putting-the-code-on-github) | Sharing the code with the dashboard team |
| [I. Troubleshooting](#i-troubleshooting) | Something looks wrong |

How to read the steps: copy **one grey box at a time** and paste it into the terminal.
On the GB10, the terminal is **Terminal** (paste with **Ctrl + Shift + V**). On Windows it is **PowerShell**
(Start menu → type `PowerShell` → open it; paste with a **right-click** or **Ctrl + V**).
Each step says what you should see. If you see something else, look in [Part I](#i-troubleshooting).

**What the app needs, in one picture**

```
 RBI website ──► PNB Regulatory Sentinel (port 8090) ──► your browser / the Top Management Dashboard
                         │
                         ▼
                 Ollama (port 11434) on a GPU
                 ├─ gpt-oss:20b  writes answers and summaries
                 └─ bge-m3       searches by meaning
```

The app and Ollama are separate programs. Both must be running. The health check script
(`scripts/check.py`) tests every link in this picture and tells you what to fix.

---

## A. Restart the GB10 after a shutdown, and what to check

Everything is set to start by itself: Docker, Ollama and the app container (`restart: unless-stopped`).
You normally only need to switch the machine on and run the check.

### A1. Switch on and log in

Press the power button, wait for the Ubuntu login screen (about 1–2 minutes), and log in.
Open **Terminal** and go to the project folder:

```bash
cd ~/Desktop/rbi-sentinel
```

### A2. Run the health check

```bash
python3 scripts/check.py
```

**You should see:** a list of lines, each starting with `[OK  ]`, `[WARN]` or `[FIX ]`, ending with
`Result: … 0 FIX` and `All good.`

Wait 2 minutes after logging in before you trust the result; the app loads the models first.
For each `[FIX ]` line, do the `->` steps written under it, then run the check again.

### A3. What the check looks at, and the same checks by hand

| # | Parameter | Command | Good value | If not |
|---|---|---|---|---|
| 1 | GPU driver answers | `nvidia-smi` | A table with the GPU name (NVIDIA GB10) and a driver version | Reboot once. Still failing: the driver needs reinstalling (IT) |
| 2 | GPU temperature | `nvidia-smi --query-gpu=temperature.gpu,power.draw,utilization.gpu --format=csv` | Below about 80 °C when busy, 30–50 °C when idle | Check the vents and airflow; a thermal shutdown is a common cause of a sudden power-off |
| 3 | Why it shut down | `journalctl -b -1 -p warning --no-pager \| tail -40` | Nothing alarming | Look for `thermal`, `Xid`, `NVRM`, `power`. Send these lines to IT if the shutdown repeats |
| 4 | Memory and disk | `free -h` and `df -h ~` | Several GB "available"; at least 15 GB free on disk | `docker system prune` frees old build layers (your data is kept) |
| 5 | Ollama running | `systemctl status ollama --no-pager` | `active (running)` | `sudo systemctl start ollama` |
| 6 | Models present | `ollama list` | `gpt-oss:20b` and `bge-m3` | `ollama pull gpt-oss:20b` and `ollama pull bge-m3` |
| 7 | Models on the GPU | `ollama ps` (after asking the app a question) | PROCESSOR column says `100% GPU` | `sudo systemctl restart ollama` |
| 8 | Docker running | `docker info --format '{{.ServerVersion}}'` | A version number | `sudo systemctl start docker` |
| 9 | App container | `docker compose ps` | `pnb-sentinel … Up … (healthy)` | `docker compose up -d`, then `docker compose logs --tail 80 sentinel` |
| 10 | App answers | `curl -s localhost:8090/api/health` | `{"status":"ok","index_chunks":…}` with a number above 0 | Wait a minute; then step 9 |
| 11 | Search model | Overview page: no yellow "keyword-hash embedder" banner. Or: `curl -s localhost:8090/api/dashboard \| python3 -c "import sys,json;print(json.load(sys.stdin)['system'])"` | `embedding_model: openai_compat:bge-m3` and `embedding_fallback: None` | The app started before Ollama was ready: `docker compose restart` |
| 12 | Language model | Settings page → **Check model** | Healthy | Steps 5–7, then click Check model again |
| 13 | RBI sources | Overview → **Sources covered** | Each source "ok", with entries read | Check the GB10 can open https://www.rbi.org.in; the app retries every 30 minutes |
| 14 | Loading progress | Overview → Sources covered → "waiting" | Goes down over time to 0 | Nothing to do: it continues by itself after a restart |
| 15 | AI summaries | Overview → AI summaries | Rises every 5 minutes until every current document has one | Nothing to do |

**What happens to work that was in progress when the power went off:** nothing is lost. Documents already
read are in the database. A sync that was interrupted simply runs again about 10 seconds after the app starts,
and documents that were still waiting are picked up in the next batches.

### A4. If the app does not come back by itself

```bash
cd ~/Desktop/rbi-sentinel
sudo systemctl start docker ollama
docker compose up -d
python3 scripts/check.py
```

### A5. Make sure everything starts by itself next time

Run once; it is harmless to repeat:

```bash
sudo systemctl enable docker ollama
```

---

## B. First install on the GB10 (Docker)

The short form is below. **START_HERE.md** has the same steps with pictures of what you should see.

### B1. Check the tools

```bash
docker --version
docker compose version
ollama --version
nvidia-smi
```

Each should print a version (and `nvidia-smi` a table). If `docker` says "permission denied":

```bash
sudo usermod -aG docker $USER
```

then log out of Ubuntu, log back in, and try again.

### B2. Download the models (about 13 GB the first time)

```bash
ollama pull gpt-oss:20b
ollama pull bge-m3
ollama list
```

### B3. Get the code

From a zip: copy `rbi-sentinel.zip` to the Desktop, then

```bash
cd ~/Desktop
unzip rbi-sentinel.zip
cd rbi-sentinel
```

From GitHub (after [Part H](#h-putting-the-code-on-github)):

```bash
cd ~/Desktop
git clone https://github.com/YOUR-GITHUB-NAME/pnb-regulatory-sentinel.git rbi-sentinel
cd rbi-sentinel
```

### B4. Settings

```bash
cp .env.example .env
```

The defaults are right for the GB10. Open it with `nano .env` only if you want to change something
(save: Ctrl + O, Enter; exit: Ctrl + X).

### B5. Build and start

```bash
docker compose up -d --build
```

The first build takes 5–10 minutes. **You should see:** `Container pnb-sentinel  Started`.

### B6. Check and open

```bash
python3 scripts/check.py
hostname -I
```

Open **http://localhost:8090** on the GB10, or **http://FIRST-NUMBER-FROM-hostname:8090** from a laptop on
the same network.

---

## C. Windows with Docker Desktop (recommended on Windows)

The app runs inside Docker exactly as on the GB10. The only difference is a separate compose file,
`docker-compose.windows.yml`, because Docker Desktop cannot use the GB10's "host network" mode.

### C1. What the PC needs

| Item | Minimum |
|---|---|
| Windows | Windows 10 22H2 or Windows 11, 64-bit |
| Memory | 16 GB RAM (32 GB if the models run on this PC) |
| Disk | 30 GB free (plus about 13 GB for the models if they run on this PC) |
| Virtualisation | Switched on in the BIOS (Task Manager → Performance → CPU → "Virtualisation: Enabled") |
| GPU (optional) | An NVIDIA GPU with 16 GB of video memory runs `gpt-oss:20b` well. Without one, see C3 and Part E |
| Admin rights | Needed once, to install Docker Desktop, Git and Ollama |

### C2. Install the programs (once)

1. **Git for Windows**: https://git-scm.com/download/win → run the installer, keep every default.
2. **Docker Desktop**: https://www.docker.com/products/docker-desktop/ → run the installer, keep
   **"Use WSL 2 instead of Hyper-V"** ticked. Restart Windows when asked. Open Docker Desktop, accept the terms,
   and wait until the bottom-left corner says **Engine running**.
3. **Python 3.12** (only to run the health check): https://www.python.org/downloads/windows/ → tick
   **"Add python.exe to PATH"** on the first screen → Install Now.
4. **Ollama for Windows** (skip if you will use the GB10's models, Part E): https://ollama.com/download →
   run `OllamaSetup.exe`. Ollama then runs in the tray next to the clock.

Check in a **new** PowerShell window:

```powershell
git --version
docker --version
docker compose version
py --version
```

Each line should print a version.

### C3. Download the models (if Ollama runs on this PC)

```powershell
ollama pull gpt-oss:20b
ollama pull bge-m3
ollama list
```

If the PC has an NVIDIA GPU, Ollama uses it automatically (check later with `ollama ps`: `100% GPU`).
Make sure the NVIDIA driver is current (GeForce Experience / NVIDIA App, or https://www.nvidia.com/drivers).

**No suitable GPU?** Either use the GB10's models over the network ([Part E](#e-using-the-gb10s-gpu-from-a-windows-pc)),
or a smaller model on this PC, for example:

```powershell
ollama pull qwen3:4b
```

and set `LLM_MODEL=qwen3:4b` in `.env` (C5). Answers will be shorter and less careful than with `gpt-oss:20b`.

### C4. Get the code

Use a folder that is **not** inside OneDrive (OneDrive syncing breaks builds), for example `C:\work`:

```powershell
mkdir C:\work -Force
cd C:\work
git clone https://github.com/YOUR-GITHUB-NAME/pnb-regulatory-sentinel.git rbi-sentinel
cd rbi-sentinel
```

(From a zip instead: right-click the zip → **Extract All…** → choose `C:\work`, then `cd C:\work\rbi-sentinel`.)

### C5. Settings

```powershell
Copy-Item .env.example .env
notepad .env
```

In Notepad, find these two lines near the top and **remove the `#`** at the start of the first one:

```
COMPOSE_FILE=docker-compose.windows.yml
# OLLAMA_URL=http://host.docker.internal:11434/v1
```

Leave `OLLAMA_URL` commented if Ollama runs on this PC. Save (Ctrl + S) and close Notepad.

`COMPOSE_FILE` makes every plain `docker compose …` command use the Windows file, so all the commands in this
manual work the same on Windows and on the GB10.

### C6. Build and start

```powershell
docker compose up -d --build
```

The first build takes 5–15 minutes. **You should see:** `Container pnb-sentinel  Started`.

If Windows asks whether Docker may use the network, choose **Allow** (private networks).

### C7. Check and open

```powershell
py scripts\check.py
```

Open **http://localhost:8090** in Edge or Chrome.

On a PC without an NVIDIA GPU, the check shows `[WARN] nvidia-smi - not found`. That is expected.

### C8. Stop and start on Windows

Docker Desktop must be running for the app to run. To start it with Windows: Docker Desktop → Settings →
General → tick **Start Docker Desktop when you sign in**. The app container then starts by itself.

```powershell
docker compose down      # stop the app
docker compose up -d     # start it again
```

---

## D. Windows without Docker

Use this only when Docker Desktop is not allowed. The same code runs directly with Python and Node.js.

### D1. Install the programs (once)

1. **Python 3.12**: https://www.python.org/downloads/windows/ → tick **"Add python.exe to PATH"** → Install Now.
   (Use 3.12. Newer versions may not have every package ready yet.)
2. **Node.js 22 LTS**: https://nodejs.org → the LTS installer, keep the defaults.
3. **Git for Windows**: https://git-scm.com/download/win.
4. **Ollama for Windows**: https://ollama.com/download (skip if you will use the GB10's models, Part E).

In a **new** PowerShell window:

```powershell
py -3.12 --version
node --version
git --version
```

### D2. Get the code and the models

As in C3 and C4.

### D3. Settings

```powershell
Copy-Item .env.example .env
notepad .env
```

Ollama on this PC: nothing to change (the defaults point at `http://localhost:11434/v1`).
Ollama on the GB10: change both of these lines to the GB10's address (Part E):

```
LLM_BASE_URL=http://10.20.30.40:11434/v1
EMBEDDING_BASE_URL=http://10.20.30.40:11434/v1
```

### D4. Start

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

The first run installs the Python packages, a headless browser and the website parts (10–15 minutes).
**You should see**, at the end: `Starting on http://localhost:8090`, then lines from `uvicorn`.

Keep this window open: closing it stops the app. Stop it with **Ctrl + C**.
If Windows Firewall asks, allow **Private networks** only.

### D5. Check and open

In a second PowerShell window:

```powershell
cd C:\work\rbi-sentinel
py scripts\check.py --no-docker
```

Then open **http://localhost:8090**. Data (database, logs) is kept in `backend\data`.

### D6. Run the automatic tests (optional)

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 test
```

**You should see:** `13 passed`. The tests use saved copies of RBI pages, so they need no internet.

---

## E. Using the GB10's GPU from a Windows PC

The app can run on Windows while the models run on the GB10. Only Ollama is shared.

> **Security:** Ollama has no password. Once it listens on the network, anyone who can reach port 11434 on the
> GB10 can use the models. Do this only on the bank's internal network, and allow only the PCs that need it (E3).

### E1. On the GB10: let Ollama listen on the network

```bash
sudo systemctl edit ollama
```

An editor opens. In the empty space between the comment lines, type:

```
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

Save (Ctrl + O, Enter) and exit (Ctrl + X). Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
hostname -I
```

Note the first number from `hostname -I`, for example `10.20.30.40`.

The app on the GB10 keeps working unchanged (it still uses `localhost`).

### E2. From the Windows PC: test the connection

```powershell
curl.exe http://10.20.30.40:11434/api/tags
```

**You should see:** text that includes `gpt-oss:20b` and `bge-m3`. If it hangs, see E3.

### E3. If the GB10's firewall is on, allow only the Windows PC

On the GB10 (replace the address with the Windows PC's; find it on Windows with `ipconfig`, "IPv4 Address"):

```bash
sudo ufw status
sudo ufw allow from 10.20.30.55 to any port 11434 proto tcp
```

If `ufw status` says `inactive`, there is no firewall on the GB10 and nothing to do; the bank's network
firewall may still block the port, in which case ask IT.

### E4. Point the Windows app at the GB10

- **With Docker Desktop (Part C):** in `.env`, set `OLLAMA_URL=http://10.20.30.40:11434/v1` (remove its `#`),
  then `docker compose up -d`.
- **Without Docker (Part D):** set `LLM_BASE_URL` and `EMBEDDING_BASE_URL` as in D3, then restart `run.ps1`.

Check:

```powershell
py scripts\check.py --ollama http://10.20.30.40:11434
```

### E5. To undo

On the GB10: `sudo systemctl revert ollama && sudo systemctl restart ollama`.

---

## F. Everyday commands, backup and restore

Run these inside the project folder (`cd ~/Desktop/rbi-sentinel` on the GB10, `cd C:\work\rbi-sentinel` on Windows).
With `COMPOSE_FILE` set (C5), the same commands work on Windows.

| I want to… | Command |
|---|---|
| Check everything | `python3 scripts/check.py` (Windows: `py scripts\check.py`) |
| Stop the app | `docker compose down` |
| Start it | `docker compose up -d` |
| Restart it | `docker compose restart` |
| Apply a change to `.env` | `docker compose up -d` |
| Apply new code or a new logo | `docker compose up -d --build` |
| Watch what it is doing | `docker compose logs -f sentinel` (Ctrl + C stops watching, the app keeps running) |
| See the last 80 log lines | `docker compose logs --tail 80 sentinel` |
| Start an RBI check now | Overview → **Check RBI now** |
| Free disk space | `docker system prune` (keeps your data volume) |

### Backup

All data (database, logs, audit trail, the Master Circular year cache) lives in one Docker volume,
`rbi-sentinel_sentinel-data`.

GB10:

```bash
docker run --rm -v rbi-sentinel_sentinel-data:/d -v "$PWD":/b alpine tar czf /b/sentinel-backup.tgz -C /d .
```

Windows (PowerShell):

```powershell
docker run --rm -v rbi-sentinel_sentinel-data:/d -v "${PWD}:/b" alpine tar czf /b/sentinel-backup.tgz -C /d .
```

This writes `sentinel-backup.tgz` in the project folder. Copy it somewhere safe. It is excluded from Git.

### Restore (replaces the current data)

```bash
docker compose down
docker run --rm -v rbi-sentinel_sentinel-data:/d -v "$PWD":/b alpine sh -c "rm -rf /d/* && tar xzf /b/sentinel-backup.tgz -C /d"
docker compose up -d
```

(On Windows write `"${PWD}:/b"` instead of `"$PWD":/b`.)

### Start again from empty

```bash
docker compose down -v
docker compose up -d
```

`-v` deletes the data volume: everything is read from the RBI website again (1–3 hours).

---

## G. Updating to new code

Your `.env` and all loaded data are kept in every method below.

### From GitHub (once Part H is done)

```bash
cd ~/Desktop/rbi-sentinel
git pull
docker compose up -d --build
python3 scripts/check.py
```

### From a zip

```bash
cd ~/Desktop
mv rbi-sentinel rbi-sentinel-old
unzip ~/Downloads/rbi-sentinel.zip
cp rbi-sentinel-old/.env rbi-sentinel/.env
cd rbi-sentinel
docker compose up -d --build
python3 scripts/check.py
```

When everything works, delete the old folder: `rm -rf ~/Desktop/rbi-sentinel-old`.

**New settings in a new version:** compare your `.env` with the new `.env.example`
(`diff .env .env.example`) and copy over any new lines you want.

---

## H. Putting the code on GitHub

Do this once, from the GB10 (or from Windows: the commands are the same in PowerShell).

### H1. Before you start: secrets stay out

`.env` holds settings and, if you ever switch e-mail or login on, passwords. It is listed in `.gitignore`,
so Git will not upload it. The steps below include a check. Never paste `.env` into GitHub, an issue,
a chat or an e-mail.

### H2. Create an empty private repository

1. Sign in at https://github.com.
2. Top right **+** → **New repository**.
3. Name: `pnb-regulatory-sentinel`. Visibility: **Private**.
4. Leave **"Add a README"**, **.gitignore** and **license** all **unticked** (the project already has them).
5. Click **Create repository**. Keep the page open; it shows the address you need, ending in `.git`.

If the bank has a GitHub organisation, create it there instead (ask who manages it), so the dashboard team
has access without your personal account.

### H3. Create a token (GitHub's password for the terminal)

GitHub does not accept your normal password in the terminal.

1. GitHub → your photo (top right) → **Settings** → **Developer settings** (bottom left) →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Name: `gb10-push`. Expiration: 90 days. Repository access: **Only select repositories** →
   `pnb-regulatory-sentinel`.
3. **Permissions** → Repository permissions → **Contents: Read and write**.
4. **Generate token** and copy it (it starts with `github_pat_`). It is shown only once; keep it in a password
   manager, not in a file in the project.

### H4. Tell Git who you are (once per machine)

On the GB10, if `git --version` says "command not found": `sudo apt install -y git`.

```bash
git config --global user.name "Your Name"
git config --global user.email "the-email-on-your-github-account"
git config --global init.defaultBranch main
```

On the GB10, also let Git remember the token so you type it only once:

```bash
git config --global credential.helper store
```

(This saves the token in `~/.git-credentials` on the GB10, readable only by your user. Leave this out if
other people use the same Ubuntu account. On Windows, Git for Windows remembers it securely by itself.)

### H5. Make the first commit

```bash
cd ~/Desktop/rbi-sentinel
git init
git add .
git status
```

**Check the list `git status` prints:**

- `.env` must **not** appear. (`.env.example` should appear; that one is safe.)
- There should be no `node_modules`, `dist`, `.venv`, `data` or `.tgz` files.

If `.env` does appear, stop and run `git rm --cached .env`, then check `.gitignore` contains a line `.env`.

```bash
git commit -m "PNB Regulatory Sentinel: first version"
```

### H6. Upload

Replace the address with the one GitHub showed you in H2:

```bash
git remote add origin https://github.com/YOUR-GITHUB-NAME/pnb-regulatory-sentinel.git
git push -u origin main
```

When asked: **Username** = your GitHub user name. **Password** = paste the token from H3
(nothing appears while you paste; that is normal). Press Enter.

**You should see:** lines ending with `branch 'main' set up to track 'origin/main'`.
Refresh the GitHub page: the files are there, and `README.md` is shown below them.

### H7. Give the dashboard team access

GitHub repository → **Settings** → **Collaborators** → **Add people** → their GitHub names.
Point them to **INTEGRATION.md** (iframe and REST API) and this manual.

### H8. Later changes

```bash
cd ~/Desktop/rbi-sentinel
git add .
git status            # .env must still not be listed
git commit -m "Describe what changed"
git push
```

---

## I. Troubleshooting

Run the health check first (`python3 scripts/check.py`, Windows `py scripts\check.py`); it names most problems.

| What you see | Likely cause | What to do |
|---|---|---|
| Browser: "This site can't be reached" | App not running, or wrong address | `docker compose ps`; if not `Up`, `docker compose up -d` and read `docker compose logs --tail 80 sentinel` |
| `docker compose ps` shows `Restarting` | The app fails at start | `docker compose logs --tail 80 sentinel` and send the last lines to the maintainer |
| Yellow banner "keyword-hash embedder" | The app started before Ollama was ready | Check `ollama list` shows `bge-m3`, then `docker compose restart` |
| Settings: language model not healthy | Ollama stopped or the model is missing | GB10: `sudo systemctl restart ollama`. Windows: quit Ollama in the tray and start it again. Then **Check model** |
| Answers very slow (minutes) | Model running on the CPU | `ollama ps` should show `100% GPU`. On the GB10, `sudo systemctl restart ollama`. On Windows, update the NVIDIA driver or use the GB10 (Part E) |
| First answer after a restart is slow | The model is being loaded into the GPU | Normal, about 30 seconds; later answers are faster |
| A source shows **failed** on Overview | The machine cannot reach rbi.org.in | Open https://www.rbi.org.in in a browser on that machine; if the bank uses a proxy, ask IT for its address |
| Master circulars "read 0 entries" | RBI changed the page | Agent traces → latest **RBI sync** → step **read master circular listing** → send its output to the maintainer |
| Build fails at `playwright install` | No access to the browser download | Allow `cdn.playwright.dev` and `playwright.azureedge.net`, then build again |
| Build fails with `libatomic.so.1` | Old Dockerfile | Use the current code (Part G); the Dockerfile installs `libatomic1` |
| Port 8090 already in use | Another program uses it | Set `PORT=8091` and `PUBLIC_URL=http://localhost:8091` in `.env`, then `docker compose up -d` |
| Windows: `docker` not recognised | Docker Desktop not installed or not started | Start Docker Desktop and wait for **Engine running**; open a new PowerShell |
| Windows: "WSL 2 installation is incomplete" | WSL missing | In an admin PowerShell: `wsl --install`, restart Windows, open Docker Desktop again |
| Windows: container cannot reach Ollama | Ollama not running, or `OLLAMA_URL` wrong | `curl.exe http://localhost:11434/api/tags` on the PC should list the models; check the `OLLAMA_URL` line in `.env` |
| Windows: `run.ps1 cannot be loaded because running scripts is disabled` | PowerShell's script policy | Start it with `powershell -ExecutionPolicy Bypass -File .\run.ps1` as written in D4 |
| Windows: `py` not recognised | Python not installed, or "Add to PATH" not ticked | Re-run the Python installer → **Modify** → tick "Add Python to environment variables" |
| Windows: `npm ci` fails | Old Node.js | Install Node.js 22 LTS, open a new PowerShell, run `run.ps1` again |
| `git push`: "Authentication failed" | Normal password used, or token lacks access | Use the token from H3 as the password; check it has **Contents: Read and write** for this repository |
| `git push`: "rejected … fetch first" | The GitHub repository was created with a README | `git pull --rebase origin main`, then `git push` |
| GB10 shuts down by itself again | Overheating or power | Part A3 rows 2–3; keep the vents clear and check the power supply and socket |

**Collecting information for the maintainer:**

```bash
python3 scripts/check.py > check.txt
docker compose logs --tail 300 sentinel > app-log.txt
```

Send `check.txt` and `app-log.txt`. They contain no passwords. Do not send `.env`.
