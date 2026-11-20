import { useRef, useState } from "react";
import type { ExtractResult, SheetPreview } from "./api";

const ACCEPT = ".docx,.pdf,.txt,.pptx,.xlsx,.csv,.json";

type Props = {
  text: string;
  onTextChange: (text: string) => void;
  file: ExtractResult | null;
  uploading: boolean;
  uploadError: string | null;
  onUpload: (file: File) => void;
  onClear: () => void;
  disabled: boolean;
};

export default function InputPanel(props: Props) {
  const { text, onTextChange, file, uploading, uploadError, onUpload, onClear, disabled } = props;
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const pick = (files: FileList | null) => {
    if (files && files[0]) onUpload(files[0]);
  };

  if (file) {
    return (
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4 rounded-lg border border-slate-200 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate font-medium text-slate-800">{file.filename}</p>
            <p className="text-sm text-slate-500">
              {file.kind === "text"
                ? `${(file.word_count ?? 0).toLocaleString("en-IN")} words`
                : `${(file.row_count ?? 0).toLocaleString("en-IN")} rows`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            className="shrink-0 rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon disabled:opacity-50"
          >
            Clear
          </button>
        </div>
        {file.notices.map((n) => (
          <p key={n} className="rounded-md bg-pnb-cream px-3 py-2 text-sm text-slate-700">
            {n}
          </p>
        ))}
        {file.kind === "text" ? (
          <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-100 bg-slate-50/50 p-4 text-sm leading-relaxed text-slate-700">
            {file.text}
          </div>
        ) : (
          file.sheets?.map((s) => <SheetTable key={s.name} sheet={s} />)
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <label className="block">
        <span className="text-sm font-medium text-slate-700">Paste text</span>
        <textarea
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          disabled={disabled}
          rows={10}
          placeholder="Paste a letter, circular or report here…"
          className="mt-2 w-full resize-y rounded-lg border border-slate-200 p-4 text-sm leading-relaxed focus:border-pnb-maroon focus:outline-none focus:ring-2 focus:ring-pnb-gold/30"
        />
      </label>

      <div className="flex items-center gap-3 text-xs uppercase tracking-wide text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />
        or
        <span className="h-px flex-1 bg-slate-200" />
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a file"
        onClick={() => !uploading && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !uploading) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!uploading) pick(e.dataTransfer.files);
        }}
        className={`cursor-pointer rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors focus-visible:outline-2 focus-visible:outline-pnb-gold ${
          dragging ? "border-pnb-gold bg-pnb-cream" : "border-slate-200 hover:border-pnb-maroon/40"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            pick(e.target.files);
            e.target.value = "";
          }}
        />
        <p className="font-medium text-pnb-maroon">
          {uploading ? "Reading file…" : "Drop a file here or click to choose"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Word, PDF, PowerPoint, Excel, CSV, JSON or text · up to 20 MB · data files up to 10,000
          rows
        </p>
      </div>
      {uploadError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {uploadError}
        </p>
      )}
    </div>
  );
}

function SheetTable({ sheet }: { sheet: SheetPreview }) {
  return (
    <div>
      <p className="mb-2 text-sm text-slate-600">
        <span className="font-medium text-slate-800">{sheet.name}</span> ·{" "}
        {sheet.row_count.toLocaleString("en-IN")} rows
        {sheet.row_count > sheet.rows.length && ` (first ${sheet.rows.length} shown)`}
      </p>
      <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-50 text-slate-600">
            <tr>
              {sheet.columns.map((c) => (
                <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, i) => (
              <tr key={i} className="border-t border-slate-100">
                {row.map((v, j) => (
                  <td key={j} className="whitespace-nowrap px-3 py-1.5 text-slate-700">
                    {v === null ? "" : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
