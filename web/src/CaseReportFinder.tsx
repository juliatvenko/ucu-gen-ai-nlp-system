import { useState } from "react";
import { getJson } from "./api";
import type { CaseReport, CaseReportSearch } from "./types";

/** Cohort search over published case reports. It only shortlists; screening decides. */
export function CaseReportFinder({ nctId, chosen, onToggle, disabled }: {
  nctId: string;
  chosen: CaseReport[];
  onToggle: (report: CaseReport, on: boolean) => void;
  disabled: boolean;
}) {
  const [found, setFound] = useState<CaseReportSearch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search() {
    setLoading(true);
    setError("");
    try {
      setFound(await getJson<CaseReportSearch>(`/api/trials/${nctId}/case-reports?k=10`));
    } catch {
      setError("The search failed. Try again.");
    }
    setLoading(false);
  }

  if (!found) {
    return (
      <div>
        <button type="button" onClick={search} disabled={disabled || loading}
          className="w-full cursor-pointer rounded-lg border border-line px-3 py-2 text-sm font-medium hover:bg-subtle disabled:cursor-default disabled:opacity-60">
          {loading ? "Searching case reports…" : "Find published case reports for this trial"}
        </button>
        {error && <p className="mt-1 text-xs text-bad" role="alert">{error}</p>}
      </div>
    );
  }
  if (!found.available) {
    return <p className="text-xs text-muted">The case reports aren't downloaded. Run <code>python -m scripts.download_data</code> to add them.</p>;
  }
  return (
    <fieldset>
      <legend className="mb-1 text-sm">Case reports that mention this trial's condition</legend>
      <p className="mb-1.5 text-xs text-muted">
        Top {found.candidates.length} of {found.searched.toLocaleString()} by keyword search, after {found.ruled_out} were ruled out by age or sex. A mention isn't a diagnosis: screening checks each one.
      </p>
      {found.candidates.length === 0 ? (
        <p className="text-xs text-muted">No case report mentions this trial's condition.</p>
      ) : (
        <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
          {found.candidates.map((r) => (
            <label key={r.id} className="flex cursor-pointer gap-2 rounded p-1 text-xs hover:bg-subtle">
              <input type="checkbox" disabled={disabled} checked={chosen.some((c) => c.id === r.id)}
                onChange={(e) => onToggle(r, e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
              <span className="min-w-0">
                <span className="font-medium">{r.id}</span>
                <span className="text-muted"> · {r.age != null ? `${Math.round(r.age)} y` : "age ?"}, {r.sex ?? "sex ?"}</span>
                {r.why && <span className="mt-0.5 block italic">“{r.why.replace(/\s+/g, " ").slice(0, 160)}{r.why.length > 160 ? "…" : ""}”</span>}
              </span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
