# PNB Data Analyzer

The Data Analyzer reads the Excel workbooks and CSV files a person shares, and writes
their summary, their pictures and their findings. The person may then ask the document
questions in words.

It is an application of its own, with its own database and its own sessions. The
Executive Intelligence Hub owns the sign-in and opens it inside its workspace, under the
name **Data Analyzer**, so the person signs in once for the whole platform.

## What it does

1. **Reads a document.** Excel workbooks (`.xlsx`, `.xlsm`) and CSV files. A workbook
   may hold several sheets; the first one is read and the names of the others are given.
2. **Describes it.** Every column is described: what kind of data it holds, how much is
   missing, how many different values it has, and the numbers in it.
3. **Draws it.** A histogram for every number, a bar chart for every column of words,
   and a map of how the numbers move with one another.
4. **Summarises it.** A model on the machine writes the summary and the findings. When no
   model is installed, the summary is written from the figures of the data alone, and the
   interface says so.
5. **Answers questions about it.** "Which branch has the highest balance?" is answered
   from the document, and the answer says plainly when the document does not hold it.

## The role

The person holds one role in each application of the platform. The Data Analyzer uses the
role the person holds in the **News Feed** (`role_news` in the `users` table of the hub):

| Role | What the person may do |
|---|---|
| `admin` | Everything: share documents, ask questions, and remove a document. |
| `user` | Share documents, ask questions and read the findings. |

The role is taken from the signed-in person and never from the request, so a browser
cannot make itself an administrator.

## Running it on its own

The application is meant to sit inside the hub, so it has no sign-in screen of its own.
It is opened from the hub, and the hub signs the person in.

```bash
cd dataanalyzer
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8095
```

The interface is served from the same address as the API. It has to be built first:

```bash
cd dataanalyzer/frontend
npm install
npm run build
```

The setup script of the platform does all of this: `./setup.sh` on Linux and macOS,
`.\setup.ps1` on Windows.

## The settings

Everything is in `dataanalyzer/.env`, which is written by `scripts/make_env.py`.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8095` | The port the application listens on. |
| `HANDOFF_SECRET` | empty | The secret the hub and this application share. It is the same value as `ANALYZER_HANDOFF_SECRET` in `backend/.env`. |
| `HANDOFF_TICKET_SECONDS` | `120` | How long a sign-in ticket stays valid. |
| `EMBED_PARENT_ORIGINS` | the address of the hub | The origins that may drive this application. |
| `CORS_ORIGINS` | the address of the hub | The origins that may call the API from a browser. |
| `FRAME_ANCESTORS` | the address of the hub | The sites that may show this application in a frame. |
| `JWT_SECRET` | empty | The key of this application's own sessions. |
| `DATA_DIR` | `data/` | Where the documents, the pictures and the database are kept. |
| `LLM_MODEL` | `auto` | The model to write with. `auto` means the best model that is installed on this machine. |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Where the model is. Ollama and vLLM both speak this way. |
| `OLLAMA_URL` | `http://localhost:11434` | Where the models of this machine are listed. |

## The model

The summary and the findings are written by a model on the machine. `LLM_MODEL=auto` means
the best model that is installed is used, and the interface says which one it is. When a
model is named but is not installed, the best one that is installed is used instead, and
the reason is shown. Set `LLM_STRICT_MODEL=true` to refuse to use anything else.

A machine without any model still works: the summary is written from the figures of the
data alone, the findings come from the rules of the application, and the pictures are
drawn as usual.

## The tests

```bash
cd dataanalyzer/backend
../.venv/bin/python -m pytest
```
