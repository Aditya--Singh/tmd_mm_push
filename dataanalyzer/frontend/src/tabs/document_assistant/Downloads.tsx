import { useState } from "react";
import { ApiError, downloadFile, exportResult, type ExtractResult, type FileResult } from "./api";

export type DownloadOption = { label: string; make: () => Promise<FileResult> };

export function isDocx(file: ExtractResult | null): boolean {
  return !!file && file.filename.toLowerCase().endsWith(".docx");
}

/** Download choices for a text result (spec section 4). A Word upload is edited in place. */
export function textDownloads(text: string, file: ExtractResult | null): DownloadOption[] {
  const source_file_id = file?.file_id;
  const txt = { label: "Text (.txt)", make: () => exportResult({ text, format: "txt", source_file_id }) };
  const docx = {
    label: isDocx(file) ? "Word (original file, edited)" : "Word (.docx)",
    make: () => exportResult({ text, format: "docx", source_file_id }),
  };
  return isDocx(file) ? [docx, txt] : [txt, docx];
}

async function save(file: FileResult) {
  await downloadFile(file.file_id, file.filename);
}

/**
 * Download buttons. Each option builds its file on the server first; if the file may have
 * lost formatting, the warnings are shown and the user confirms before downloading.
 */
export default function Downloads({ options }: { options: DownloadOption[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [pending, setPending] = useState<FileResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pick = async (option: DownloadOption) => {
    setBusy(option.label);
    setError(null);
    setPending(null);
    try {
      const file = await option.make();
      if (file.warnings.length === 0) await save(file);
      else setPending(file);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The file could not be prepared.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-500">Download:</span>
        {options.map((o) => (
          <button
            key={o.label}
            type="button"
            onClick={() => pick(o)}
            disabled={busy !== null}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:border-pnb-maroon hover:text-pnb-maroon disabled:opacity-50"
          >
            {busy === o.label ? "Preparing…" : o.label}
          </button>
        ))}
      </div>
      {pending && (
        <div role="alert" className="rounded-md border border-pnb-gold/40 bg-pnb-cream p-4 text-sm">
          <p className="font-medium text-slate-800">Before you download</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
            {pending.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <div className="mt-3 flex gap-3">
            <button
              type="button"
              onClick={() => {
                void save(pending).then(() => setPending(null));
              }}
              className="rounded-md bg-pnb-maroon px-4 py-1.5 font-medium text-white hover:bg-pnb-maroon-dark"
            >
              Download {pending.filename}
            </button>
            <button
              type="button"
              onClick={() => setPending(null)}
              className="text-slate-500 hover:text-pnb-maroon"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
