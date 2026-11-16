import { useEffect, useRef, useState } from "react";
import { getJson } from "./api";
import type { Criterion, TrialBrief, TrialDetails } from "./types";
import { Card, Pill, structureNote } from "./ui";

export function eligibilityLine(t: TrialBrief): string {
  const years = (n: number) => (n < 1 ? `${Math.round(n * 12)} months` : `${Math.round(n)}`);
  const ages =
    t.min_age != null && t.max_age != null ? `Ages ${years(t.min_age)}–${years(t.max_age)}`
      : t.min_age != null ? `Ages ${years(t.min_age)} and over`
        : t.max_age != null ? `Ages up to ${years(t.max_age)}` : "Any age";
  const sex = t.sex === "FEMALE" ? "women only" : t.sex === "MALE" ? "men only" : "all sexes";
  return `${ages}, ${sex}`;
}

function statusLabel(status: string): string {
  return status ? status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ") : "Status unknown";
}

/** Suggestions, live search, and an ID box in one place. Calls onPick with an NCT ID. */
export function TrialPicker({ onPick, disabled }: { onPick: (nctId: string) => void; disabled: boolean }) {
  const [suggested, setSuggested] = useState<(TrialBrief & { note: string })[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TrialBrief[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const latest = useRef(0);

  useEffect(() => {
    getJson<(TrialBrief & { note: string })[]>("/api/trials/suggested").then(setSuggested).catch(() => setSuggested([]));
  }, []);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) { setResults(null); setError(""); return; }
    const call = ++latest.current;
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const found = await getJson<TrialBrief[]>(`/api/trials/search?q=${encodeURIComponent(text)}`);
        if (call === latest.current) { setResults(found); setError(""); }
      } catch {
        if (call === latest.current) { setResults(null); setError("Search failed. ClinicalTrials.gov may be slow, so try again."); }
      }
      if (call === latest.current) setSearching(false);
    }, 450);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div className="space-y-3">
      {suggested.length > 0 && (
        <div>
          <label htmlFor="suggested" className="mb-1 block text-sm">Suggested trials</label>
          <select
            id="suggested"
            value=""
            disabled={disabled}
            onChange={(e) => e.target.value && onPick(e.target.value)}
            className="w-full rounded-lg border border-line bg-page p-2 text-sm"
          >
            <option value="">Choose a trial that fits an example</option>
            {suggested.map((t) => <option key={t.nct_id} value={t.nct_id}>{t.note}: {t.title.slice(0, 60)}…</option>)}
          </select>
        </div>
      )}
      <div>
        <label htmlFor="trial-search" className="mb-1 block text-sm">Or search by condition or NCT ID</label>
        <input
          id="trial-search"
          type="search"
          value={query}
          disabled={disabled}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Crohn's disease, or NCT07109700"
          autoComplete="off"
          className="w-full rounded-lg border border-line bg-page px-3 py-2 text-sm placeholder:text-muted"
        />
        <p aria-live="polite" className="mt-1 text-xs text-muted">
          {searching ? "Searching recruiting trials…" : error ? <span className="text-bad">{error}</span>
            : results && !results.length ? "No recruiting trials found. Try a broader condition." : ""}
        </p>
        {results && results.length > 0 && (
          <ul className="mt-1 max-h-72 space-y-1 overflow-y-auto rounded-lg border border-line p-1">
            {results.map((t) => (
              <li key={t.nct_id}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => { onPick(t.nct_id); setQuery(""); setResults(null); }}
                  className="w-full cursor-pointer rounded-md p-2 text-left transition hover:bg-subtle"
                >
                  <span className="block text-sm font-medium leading-snug">{t.title}</span>
                  <span className="mt-0.5 block text-xs text-muted">
                    {t.nct_id} · {t.conditions.slice(0, 2).join(", ") || "No conditions listed"} · {eligibilityLine(t)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function CriteriaList({ criteria }: { criteria: Criterion[] }) {
  return (
    <>
      {(["inclusion", "exclusion"] as const).map((kind) => {
        const items = criteria.filter((c) => c.kind === kind);
        if (!items.length) return null;
        return (
          <div key={kind} className="mt-3">
            <h4 className="mb-1.5 text-xs font-semibold text-muted">{kind === "inclusion" ? "Inclusion" : "Exclusion"} ({items.length})</h4>
            <ol className="space-y-1.5">
              {items.map((c) => (
                <li key={c.id} className="rounded-lg border border-line px-3 py-2 text-sm">
                  {c.screening_only && <span className="mb-1 block"><Pill tone="bg-subtle text-muted">Confirmed at screening, not checked</Pill></span>}
                  {structureNote(c) && <span className="mb-1 block"><Pill tone="bg-subtle text-muted">{structureNote(c)}</Pill></span>}
                  {c.text}
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </>
  );
}

/** The chosen trial: what it is, who it's for, and the criteria the engine will check. */
export function TrialCard({ trial, onChange, criteriaOpen }: { trial: TrialDetails; onChange: () => void; criteriaOpen: boolean }) {
  const [more, setMore] = useState(false);
  const screening = trial.criteria.filter((c) => c.screening_only).length;
  const inclusion = trial.criteria.filter((c) => c.kind === "inclusion").length;
  const long = trial.summary.length > 320;
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <a href={`https://clinicaltrials.gov/study/${trial.nct_id}`} target="_blank" rel="noreferrer" className="text-xs font-medium text-accent hover:underline">{trial.nct_id} ↗</a>
          <h2 className="mt-0.5 font-semibold leading-snug">{trial.title}</h2>
        </div>
        <button type="button" onClick={onChange} className="cursor-pointer rounded-lg border border-line px-2.5 py-1 text-xs font-medium hover:bg-subtle">Change trial</button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Pill tone={trial.status === "RECRUITING" ? "bg-good-soft text-good" : "bg-subtle text-muted"}>{statusLabel(trial.status)}</Pill>
        <Pill tone="bg-subtle text-muted">{eligibilityLine(trial)}</Pill>
        {trial.conditions.slice(0, 3).map((c) => <Pill key={c} tone="bg-accent-soft">{c}</Pill>)}
      </div>
      {trial.summary && (
        <div className="mt-3 text-sm leading-relaxed">
          <p className="whitespace-pre-wrap">{long && !more ? `${trial.summary.slice(0, 320).trimEnd()}…` : trial.summary}</p>
          {long && <button type="button" onClick={() => setMore(!more)} className="mt-1 cursor-pointer text-xs font-medium text-accent hover:underline">{more ? "Show less" : "Show more"}</button>}
        </div>
      )}
      {trial.criteria.length > 0 ? (
        <details open={criteriaOpen} className="mt-4 border-t border-line pt-3">
          <summary className="cursor-pointer text-sm font-medium">
            Criteria to be checked: {trial.criteria.length - screening} of {trial.criteria.length}
            <span className="font-normal text-muted"> ({inclusion} inclusion, {trial.criteria.length - inclusion} exclusion{screening ? `, ${screening} confirmed at screening` : ""})</span>
          </summary>
          <p className="mt-2 text-xs text-muted">This is how the system split the trial's eligibility text. Each item is checked separately against every patient.</p>
          <CriteriaList criteria={trial.criteria} />
        </details>
      ) : (
        <p className="mt-4 text-sm text-warn">This trial lists no eligibility criteria, so there's nothing to check.</p>
      )}
    </Card>
  );
}
