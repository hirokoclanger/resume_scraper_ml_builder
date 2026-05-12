// Top form: company, title, JD textarea, Build button.

type Props = {
  jd: string; setJd: (s: string) => void;
  company: string; setCompany: (s: string) => void;
  title: string; setTitle: (s: string) => void;
  onBuild: () => void;
  busy: boolean;
};

export function JdInput(p: Props) {
  return (
    <div className="bg-white rounded-lg border p-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-semibold mb-1">Company</label>
          <input
            className="w-full px-3 py-2 border rounded text-sm"
            value={p.company} onChange={(e) => p.setCompany(e.target.value)}
            placeholder="Acme GmbH"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs font-semibold mb-1">Job title (mirror the listing verbatim)</label>
          <input
            className="w-full px-3 py-2 border rounded text-sm"
            value={p.title} onChange={(e) => p.setTitle(e.target.value)}
            placeholder="Senior IT Portfolio Manager"
          />
        </div>
      </div>
      <label className="block text-xs font-semibold mb-1 mt-3">Job description</label>
      <textarea
        className="w-full px-3 py-2 border rounded font-mono text-xs"
        rows={10}
        value={p.jd} onChange={(e) => p.setJd(e.target.value)}
        placeholder="Paste the full job description here…"
      />
      <div className="flex items-center gap-3 mt-3">
        <button
          className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded font-medium disabled:bg-gray-400"
          disabled={p.busy || p.jd.trim().length < 20}
          onClick={p.onBuild}
        >Build editable composition →</button>
        <span className="text-xs text-gray-500">{p.jd.length} chars</span>
      </div>
    </div>
  );
}
