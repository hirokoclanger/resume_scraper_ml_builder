// Bottom sticky bar: variant + PDF/DOCX render buttons + last-rendered hint.

type Props = {
  busy: boolean;
  onRender: (fmt: "pdf" | "docx", variant: string) => Promise<void>;
  lastRender: string | null;
};

export function ExportBar({ busy, onRender, lastRender }: Props) {
  return (
    <div className="bg-white border rounded-lg p-4 mt-4 flex flex-wrap items-center gap-2 sticky bottom-2 shadow-sm">
      <button className="bg-purple-600 text-white px-3 py-2 rounded text-sm disabled:bg-gray-400"
              disabled={busy} onClick={() => onRender("pdf", "metrics")}>Render Metrics PDF</button>
      <button className="bg-teal-700 text-white px-3 py-2 rounded text-sm disabled:bg-gray-400"
              disabled={busy} onClick={() => onRender("pdf", "leadership")}>Render Leadership PDF</button>
      <button className="bg-amber-700 text-white px-3 py-2 rounded text-sm disabled:bg-gray-400"
              disabled={busy} onClick={() => onRender("pdf", "tooling")}>Render Tooling PDF</button>
      <span className="w-px h-6 bg-gray-200 mx-2"/>
      <button className="bg-green-700 text-white px-3 py-2 rounded text-sm disabled:bg-gray-400"
              disabled={busy} onClick={() => onRender("docx", "leadership")}>Export .docx</button>
      <span className="text-xs text-gray-500 ml-auto">
        {lastRender ? (
          <>Last rendered: <a className="text-purple-700 underline" href={`/api/tailored/${lastRender}`} target="_blank" rel="noreferrer">{lastRender}</a></>
        ) : busy ? "Rendering…" : "—"}
      </span>
    </div>
  );
}
