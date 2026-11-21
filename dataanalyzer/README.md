# PNB Employee Productivity Tool — the Data Analyzer

The Data Analyzer is the **PNB Employee Productivity Tool**: a document assistant that
reads a document on this machine, and then works on it in words — a summary, a rewrite,
a spelling and grammar check, or a conversation about what is in a spreadsheet.

It is an application of its own, with its own API and its own sessions. The Executive
Intelligence Hub owns the sign-in and opens it inside its workspace, under the name
**Data Analyzer**, so the person signs in once for the whole platform.

The tool itself is the one published at
`https://github.com/Aditya--Singh/employee-productivity`, imported as it is.

## What it does

The tool is one page with four tools. The hub draws the same four in its own rail, under
the **Data Analyzer** card, so the person may go straight to one of them:

| Tool | What it does |
| --- | --- |
| **Proofread** | Spelling, grammar, punctuation and bank usage are checked. The suggestions that may be taken safely are offered as "Accept all"; the rest are offered one by one. |
| **Rewrite** | A passage is rewritten — more polite, more formal, shorter — and the result can be compared with the original, word by word. |
| **Summarize** | A model on this machine writes the summary of the document. |
| **Ask about data** | A question about a spreadsheet is answered from the spreadsheet: the numbers are computed with pandas and the model is asked to explain them, so an answer that does not match the figures is not given. |

Everything is done with the document that is open:

1. **Extracts.** Upload a Word document, a PDF, a PowerPoint, a spreadsheet, a CSV, a
   JSON file or a plain text file. The text is read out of it, and a spreadsheet is
   read sheet by sheet.
2. **Works on it.** Summarise it, rewrite it, check it, or ask questions about it.
3. **Exports.** The result is downloaded as a text file or a Word document, and the
   edits are written back into the original file where the format allows it.

Each tool has an address of its own (`/#/proofread`, `/#/rewrite`, `/#/summarize`,
`/#/data`), so the hub may send the person straight to one of them.

The upstream's **Circular Analyzer** and **Coming Soon** screens are not part of the tool
as it is offered here: the first was a placeholder, and the second an announcement.

## What the view shows

The view starts with the four tools, and nothing else is above them: the hub draws the
chrome of the platform, so the tool shows no banner of its own. The only thing beside the
tools is a small sign at the right, which says whether the services of this machine are
answering — **Services online**, **Checking services…** or **Backend offline**.

Opened on its own, without the hub around it, the tool says so and asks to be opened from
the dashboard.

## Nothing leaves this machine

The model server and the grammar checker are both local services. The tool refuses to
send anything to a host that is not on this machine, so a document stays here.

| Service | Address | What it is for | If it is not running |
| --- | --- | --- | --- |
| Ollama | `http://localhost:11434` | the summaries, rewrites and the answers | the tool starts, and says that the model is not running |
| LanguageTool | `http://localhost:8120` | the spelling and grammar check | the tool starts, and the proofreader says that the grammar check needs LanguageTool |

The upstream runs LanguageTool in Docker. The setup does **not** start it: the grammar
check is optional, and everything else in the tool works without it.

## The role

The person holds one role in each application of the platform. The Data Analyzer uses the
role the person holds in the **News Feed** (`role_news` in the `users` table of the hub):

| Role | What the person may do |
| --- | --- |
| `admin` | everything a reader may do, and may delete a document and its file |
| `user` | may extract, summarise, rewrite, proofread, export, ask about a spreadsheet and download the result |

The hub states the role; the tool does not invent one. The tool keeps **no accounts of
its own**: there is no second sign-in, and no second password.

## How it is signed in

The hub embeds this app in a frame and owns the sign-in:

1. The hub asks this server, on the person's behalf, for a **single-use ticket**. The
   shared secret stays on the hub's server, so a browser can never ask for one.
2. The ticket is handed to the frame over the message bridge. It never appears in a URL.
3. The frame swaps the ticket for a **token of this app**, and every call carries it.

The ticket can be spent once only, and it is short-lived. A ticket that is copied out of
a message cannot be used a second time.

## The settings

`dataanalyzer/.env` is written by the setup script. The keys that matter:

| Key | What it is |
| --- | --- |
| `PORT` | the port the app listens on (8095) |
| `JWT_SECRET` | the app's own signing key for the tokens it issues |
| `HANDOFF_SECRET` | the secret the hub and this app share (the hub has the same value) |
| `HANDOFF_TICKET_SECONDS` | how long a ticket lives (120) |
| `FRAME_ANCESTORS` | who may frame this app — a list of addresses, separated by commas or by spaces |
| `EMBED_PARENT_ORIGINS` | who may drive it over the message bridge |
| `CORS_ORIGINS` | who may call it from a browser |
| `OLLAMA_URL` | the local model server |
| `OLLAMA_MODEL` | the model to use — the setup writes the best model that is really installed |
| `OLLAMA_NUM_CTX` | the size of the model's context window |
| `LANGUAGETOOL_URL` | the optional grammar checker |
| `LANGUAGETOOL_LANGUAGE` | the language it checks |
| `MAX_UPLOAD_MB` | the largest document that is accepted |
| `DATA_DIR` | where the uploaded documents are kept |

## Running it on its own

The environment of the tool is in `dataanalyzer/.venv`, one folder above the
backend:

```bash
cd dataanalyzer/backend
../.venv/bin/python -m uvicorn app.main:app --port 8095
```

On Windows:

```powershell
cd dataanalyzer\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8095
```

The interface is built once and served from the same address:

```bash
cd dataanalyzer/frontend
npm install
npm run build
```

Opened on its own, the tool has no hub to sign the person in, and says so. It is meant
to be opened from the dashboard.

## The tests

```bash
cd dataanalyzer/backend
../.venv/bin/python -m pytest
```

On Windows:

```powershell
cd dataanalyzer\backend
..\.venv\Scripts\python.exe -m pytest
```

The upstream's own tests are here, plus the tests for the bridge to the hub and for
the routes of the four tools.

The interface has its own tests as well:

```bash
cd dataanalyzer/frontend
npm test
```
