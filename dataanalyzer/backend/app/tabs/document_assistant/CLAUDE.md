# Document Assistant (Tab 1)

Full spec: `docs/specs/tab1-document-assistant.md`. Read it before changing this tab.

## Scope
- Modes: Proofread, Rewrite, Summarize, Draft, Ask about data. British English (en-GB) only.
- Inputs: pasted text, DOCX, PDF, TXT, PPTX, XLSX, CSV, JSON. About 20 pages or 10,000 rows max.
- Frontend lives in `frontend/src/tabs/document_assistant/`.

## Rules for this tab
- Build in the seven phases in spec section 9. Test and commit each phase before the next.
- Use `core/ollama.py` for the LLM and `core/uploads.py` for every upload. Never call Ollama
  or LanguageTool with ad-hoc clients elsewhere.
- Every Ollama request carries `num_ctx` (default 32768). Never let a prompt be truncated
  silently; reject it as too long instead.
- Stream all model text output (server-sent events).
- Never add facts, figures, names or account numbers that are not in the user's input.
- Data questions: the model picks an operation from the allowlist; pandas computes it.
  Never execute model-generated code.
- Edits to DOCX, PPTX and XLSX are made in place. Spec section 5 lists exactly what formatting
  is kept and what may be lost; warn the user before a lossy download. Edited PDFs come out as
  a rebuilt PDF or a DOCX.
- New documents get a text-only PNB header in maroon with a gold rule. No logo.
- No server-side history in v1. Work lives in the browser session. Uploaded and generated
  files are deleted from the server 4 hours after upload. No database.
- Tests mock Ollama, LanguageTool and Tesseract. Use generated fixtures or `samples/`, never
  `private/`.
- New libraries listed in the spec still need approval before they are added. Only permissive
  licences (MIT, BSD, Apache); no AGPL or LGPL libraries.
