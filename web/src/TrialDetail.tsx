import { useMemo, useState } from "react";
import type { TrialVerdict } from "./types";
import { Card, CriterionRow, RulesPill, VerdictPill } from "./ui";

type Filter = "all" | "blocking" | "unknown" | "decided";

export function TrialDetail({ verdict, activeId, onSelect }: {
  verdict: TrialVerdict;
  activeId: string | null;
  onSelect: (id: string, quote: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>(verdict.blockers.length ? "blocking" : "all");
  const checks = useMemo(() => new Map(verdict.checks.map((c) => [c.criterion_id, c])), [verdict]);
  const blockers = useMemo(() => new Set(verdict.blockers), [verdict]);
  const missing = useMemo(() => new Set(verdict.missing), [verdict]);

  const counts = {
    all: verdict.criteria.length,
    blocking: verdict.blockers.length,
    unknown: verdict.missing.length,
    decided: verdict.criteria.filter((c) => !c.screening_only && !missing.has(c.id)).length,
  };
  const labels: Record<Filter, string> = { all: "All", blocking: "Blocking", unknown: "Unknown", decided: "Decided" };
  const visible = verdict.criteria.filter((c) => {
    if (filter === "blocking") return blockers.has(c.id);
    if (filter === "unknown") return missing.has(c.id);
    if (filter === "decided") return !c.screening_only && !missing.has(c.id);
    return true;
  });

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <a href={`https://clinicaltrials.gov/study/${verdict.trial.nct_id}`} target="_blank" rel="noreferrer" className="text-xs font-medium text-accent hover:underline">
            {verdict.trial.nct_id} ↗
          </a>
          <h3 className="mt-0.5 font-semibold leading-snug">{verdict.trial.title}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {verdict.fallback && <RulesPill />}
          <VerdictPill verdict={verdict.verdict} />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5" role="group" aria-label="Filter criteria">
        {(Object.keys(labels) as Filter[]).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
            className={`cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition ${filter === key ? "bg-ink text-page" : "bg-subtle text-muted hover:text-ink"}`}
          >
            {labels[key]} {counts[key]}
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">Select a criterion with a quote to highlight it in the patient description.</p>

      {(["inclusion", "exclusion"] as const).map((kind) => {
        const items = visible.filter((c) => c.kind === kind);
        if (!items.length) return null;
        return (
          <div key={kind} className="mt-4">
            <h4 className="mb-2 text-xs font-semibold text-muted">{kind === "inclusion" ? "Inclusion criteria" : "Exclusion criteria"}</h4>
            <div className="space-y-2">
              {items.map((c) => (
                <CriterionRow
                  key={c.id}
                  criterion={c}
                  check={checks.get(c.id)}
                  blocks={blockers.has(c.id)}
                  active={activeId === c.id}
                  onSelect={() => onSelect(c.id, checks.get(c.id)?.evidence ?? "")}
                />
              ))}
            </div>
          </div>
        );
      })}
      {!visible.length && <p className="mt-4 text-sm text-muted">No criteria in this view.</p>}
    </Card>
  );
}
