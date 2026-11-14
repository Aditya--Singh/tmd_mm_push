# Start here: running PNB Regulatory Sentinel, step by step

Follow the steps in order. Each step says **what to type**, **what you should see**, and **what to do if it looks different**.
Type the commands in the **Terminal** on the GB10 (Ubuntu). Copy one grey box at a time, paste it with
**Ctrl + Shift + V**, and press **Enter**.

Time needed: about 30 minutes the first time, most of it waiting for downloads.

> **Other situations are in [MANUAL.md](MANUAL.md):** restarting after the GB10 was switched off (and what to check),
> running on **Windows**, using the GB10's GPU from a Windows PC, backups, updates, and putting the code on **GitHub**.

---

## Before you start — a checklist

- [ ] You are on the GB10 machine (Ubuntu) and can open a Terminal.
- [ ] Docker and Ollama are installed (they already are on your GB10).
- [ ] The GB10 can reach the internet: `rbi.org.in`, and, for the first build only, Docker Hub, PyPI, npm and the Playwright browser download (cdn.playwright.dev).
- [ ] You have the file **rbi-sentinel.zip**.

---

## Step 1 — Put the project on the GB10

1. Copy `rbi-sentinel.zip` to the GB10's **Desktop** (USB stick, or download it there).
2. In the Terminal, type:

```bash
cd ~/Desktop
unzip rbi-sentinel.zip
cd rbi-sentinel
ls
```

**You should see:** `backend  docker-compose.yml  docker-compose.windows.yml  Dockerfile  frontend  INTEGRATION.md  MANUAL.md  README.md  run.ps1  run.sh  scripts  START_HERE.md`

**If it says "unzip: command not found":** run `sudo apt install -y unzip` and try again.

> From now on, every command is typed **inside this folder**. If you open a new Terminal later, first type `cd ~/Desktop/rbi-sentinel`.

---

## Step 2 — Check that Docker works

```bash
docker --version
docker compose version
```

**You should see:** two lines with version numbers.

**If you see "permission denied":** run the line below, then **log out of Ubuntu and log back in**, and repeat Step 2.

```bash
sudo usermod -aG docker $USER
```

---

## Step 3 — Download the two AI models

The app uses two models that run on the GB10 itself, so no circular text leaves the machine:
one to **write answers and summaries** (`gpt-oss:20b`), and one to **search by meaning** (`bge-m3`).

```bash
ollama pull gpt-oss:20b
ollama pull bge-m3
ollama list
```

**You should see:** both names in the list. The first download is about 13 GB, so it can take a while.

Check that Ollama answers:

```bash
curl -s http://localhost:11434/v1/models
```

**You should see:** a line of text that includes `gpt-oss:20b` and `bge-m3`.

**If you see "Connection refused":** start Ollama with `sudo systemctl start ollama` and try again.

---

## Step 4 — Fill in the settings file

Login and e-mail are **switched off** in this version (the app will sit inside the Top Management Dashboard),
so there is almost nothing to fill in.

```bash
cp .env.example .env
```

That's it. The defaults read Notifications, Press Releases, **every financial year of Master Circulars** and
Master Directions, use `gpt-oss:20b` and `bge-m3` from Ollama, and open on port **8090**.

(Only if you later want login or e-mail: open the file with `nano .env`, set `AUTH_ENABLED=true` and/or
`EMAIL_ENABLED=true`, and fill in that section. Save with Ctrl + O, Enter, Ctrl + X.)

---

## Step 5 — (nothing to do)

The old Gmail app-password step is not needed while e-mail is off.

---

## Step 6 (optional) — Add the official PNB logo

The app shows a plain "PNB" badge until you add the real logo. Get the official logo file from the bank's brand or
corporate communications team (PNG or SVG) and copy it to:

```
frontend/public/brand/logo.png
```

You can skip this and add it later; just repeat Step 7 afterwards.

---

## Step 7 — Start the app

```bash
docker compose up -d --build
```

The first time, this takes **5–10 minutes**: it builds the website and installs everything inside a container.
Later starts take seconds.

**You should see**, at the end: `Container pnb-sentinel  Started`

Check that it is running:

```bash
docker compose ps
```

**You should see:** `pnb-sentinel` with status `Up` (after about a minute it changes to `Up (healthy)`).

Run the health check. Every line should say `OK` (a `WARN` is information only; for a `FIX`, do what it says):

```bash
python3 scripts/check.py
```

To watch what the agents are doing right now (press **Ctrl + C** to stop watching; the app keeps running):

```bash
docker compose logs -f sentinel
```

---

## Step 8 — Open it in the browser

- **On the GB10 itself:** open Chromium and go to **http://localhost:8090**
- **From your laptop on the same network:** find the GB10's address with `hostname -I` (take the first number,
  e.g. `10.20.30.40`) and open **http://10.20.30.40:8090**

There is no sign-in page: the app opens straight on Overview.

---

## Step 9 — Watch the first load

About 10 seconds after the app starts, it checks the RBI website by itself and keeps going until everything is
loaded. Look at **Overview → Sources covered**:

| Source | First time |
|---|---|
| Notifications | about 10–20 recent items |
| Press releases | about 10–20 recent items |
| Master circulars | **every financial year**, 2026-27 back to the Archives. A hidden browser clicks each year link, so the first read takes a few minutes |
| Master directions | about 250 documents |

Documents are read 60 at a time, one batch straight after another, so the whole first load takes roughly
1–3 hours. You can use the app while it loads.

**AI summaries:** every current document gets its own AI summary in the background (a few every 5 minutes), and
straight away when you open a circular that does not have one yet. Overview shows how many are done.

**Older versions:** RBI reissues each Master Circular every year. The newest version is used for answers;
older years are kept, labelled **Older version**, and searchable when you tick **Include older yearly versions**
in the Assistant or untick **Latest versions only** on the Circulars page.

---

## Step 10 — Check that all years were read

Open **Circulars**, choose **Master circulars**, then pick a year such as **2025-2026** in the year menu.
You should see that year's list, the same as on the RBI page.

If only the current year appears, open **Agent traces**, click the latest **RBI sync**, then the step
**read master circular listing**. Its output lists each year and how many entries were read, or the error.
Send that to whoever maintains the code.

---

## Step 11 — Try it

Click **Assistant** and ask:

- "What is new from the RBI this week, and what needs action?"
- "Summarise the Master Circular on credit facilities to SCs and STs"
- "Under the master direction, when does a term loan become an NPA?"
- "Remember that I review circulars for the compliance team"
- "What does the Master Circular on housing finance say about loan-to-value ratios?"

On any circular's page, **Chat with this circular** opens the Assistant limited to that one document.

Click a small numbered circle in an answer to see the exact paragraph it came from. The **Routing slip** on the
right shows each agent that handled your question.

---

## Everyday commands

Always type these inside the `rbi-sentinel` folder (`cd ~/Desktop/rbi-sentinel`).

| I want to… | Type |
|---|---|
| Stop the app | `docker compose down` |
| Start it again | `docker compose up -d` |
| Apply a change I made to `.env` | `docker compose up -d` |
| Apply a code change or a new logo | `docker compose up -d --build` |
| See what it is doing | `docker compose logs -f sentinel` (Ctrl + C to stop watching) |
| Check that it is running | `docker compose ps` |
| Back up all data (database, logs, e-mails) | `docker run --rm -v rbi-sentinel_sentinel-data:/d -v "$PWD":/b alpine tar czf /b/sentinel-backup.tgz -C /d .` |

The app starts by itself after the GB10 restarts. After a shutdown or power cut, log in, wait 2 minutes and run
`python3 scripts/check.py`; **MANUAL.md, Part A** explains each check.

---

## Something went wrong?

| What you see | What it means | What to do |
|---|---|---|
| Browser says "This site can't be reached" | The app is not running, or the wrong address | `docker compose ps`; if not `Up`, run `docker compose up -d` and read `docker compose logs sentinel` |
| Overview: a source shows **failed** | The GB10 could not reach rbi.org.in | Check the internet; the app retries every 30 minutes by itself |
| Master circulars or directions show **read 0 entries** | RBI changed that page's layout | Open **Agent traces**, open the latest "RBI sync", click the Watcher step and send its output to whoever maintains the code |
| Yellow banner about "keyword-hash embedder" | The search model could not load | Check `ollama list` shows `bge-m3`, then `docker compose restart` |
| Settings says the language model is not healthy | Ollama is not answering | `sudo systemctl restart ollama`, then click **Check model** in Settings |
| Answers are slow | Normal for the first question after a restart (the model is loading) | Later answers are faster |
| Build fails at "playwright install" | The GB10 cannot download the browser | Check internet access to cdn.playwright.dev, then run the build again |
| Port 8090 is already used | Another program uses that port | Change `PORT=8090` and `PUBLIC_URL` in `.env` to e.g. `8091`, then `docker compose up -d` |

---

## Running without Docker (optional)

On a Linux machine with Python 3.12 and Node.js 22:

```bash
cp .env.example .env
./run.sh                  # builds everything and starts on http://localhost:8090
```

On Windows: see **MANUAL.md, Part C** (Docker Desktop) or **Part D** (`run.ps1`, no Docker).

`./run.sh test` runs the automatic tests (they use saved copies of RBI pages, no internet needed).

---

## Updating to a new version of the code

Your settings (`.env`) and all loaded data are kept.

```bash
cd ~/Desktop
mv rbi-sentinel rbi-sentinel-old
unzip ~/Downloads/rbi-sentinel.zip          # use the new zip's exact name
cp rbi-sentinel-old/.env rbi-sentinel/.env
cd rbi-sentinel
docker compose up -d --build
```

---

## Handing it to the dashboard team

See **INTEGRATION.md**: an iframe snippet (`?embed=1`) and the REST API.
