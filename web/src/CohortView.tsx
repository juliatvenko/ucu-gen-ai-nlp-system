import { useState } from "react";
import { getJson, postStream } from "./api";
import { CaseReportFinder } from "./CaseReportFinder";
import { TrialDetail } from "./TrialDetail";
import { TrialCard, TrialPicker } from "./TrialPicker";
import type { CaseReport, Progress, TrialDetails, TrialVerdict, Verdict, Vignette } from "./types";
import { Button, Card, Citation, FallbackNotice, PatientText, ProgressBar, RulesPill, VerdictPill } from "./ui";

const ORDER: Record<Verdict, number> = { likely_eligible: 0, needs_more_data: 1, insufficient_data: 2, not_eligible: 3 };

export function CohortView({ vignettes }: { vignettes: Vignette[] }) {
  const [trial, setTrial] = useState<TrialDetails | null>(null);
  const [loadingTrial, setLoadingTrial] = useState(false);
  const [trialError, setTrialError] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [reports, setReports] = useState<CaseReport[]>([]);
  const [pasted, setPasted] = useState("");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [results, setResults] = useState<Record<string, TrialVerdict> | null>(null);
  const [patients, setPatients] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [active, setActive] = useState<{ id: string; quote: string } | null>(null);

  async function pick(nctId: string) {
    setLoadingTrial(true);
    setTrialError("");
    setResults(null);
    setSelected(null);
    setActive(null);
    try {
      setTrial(await getJson<TrialDetails>(`/api/trials/${nctId}`));
    } catch {
      setTrial(null);
      setTrialError(`Couldn't load ${nctId}. Check the ID, or try again if ClinicalTrials.gov is slow.`);
    }
    setLoadingTrial(false);
  }

  function changeTrial() {
    setTrial(null);
    setReports([]);
    setResults(null);
    setSelected(null);
    setActive(null);
    setError("");
  }
  const pastedLines = pasted.split("\n").map((l) => l.trim()).filter(Boolean);
  const count = chosen.length + reports.length + pastedLines.length;

  async function run() {
    const input: Record<string, string> = {};
    chosen.forEach((c) => { input[c] = vignettes.find((v) => v.id === c)?.text ?? ""; });
    reports.forEach((r) => { input[r.id] = r.text; });
    pastedLines.forEach((line, i) => { input[`pasted-${i + 1}`] = line; });
    setPatients(input);
    setError("");
    setResults(null);
    setActive(null);
    setSelected(null);
    setProgress({ stage: "check", done: 0, total: count });
    try {
      await postStream("/api/cohort", { nct_id: trial!.nct_id, patients: input }, (event, data) => {
        if (event === "stage") setProgress(data);
        if (event === "result") {
          const r: Record<string, TrialVerdict> = data.result;
          setResults(r);
          setSelected(sorted(r)[0]?.[0] ?? null);
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
    setProgress(null);
  }

  const rows = results ? sorted(results) : [];
  const current = selected && results ? results[selected] : null;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(320px,400px)_minmax(0,1fr)]">
      <div className="space-y-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
        <Card className="p-5">
          <h2 className="font-semibold">Trial and patients</h2>
          <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); run(); }}>
            {trial ? (
              <p className="rounded-lg bg-subtle px-3 py-2 text-sm"><span className="font-medium">{trial.nct_id}</span> <span className="text-muted">is selected. Its details are <span className="lg:hidden">below</span><span className="hidden lg:inline">on the right</span>.</span></p>
            ) : (
              <TrialPicker onPick={pick} disabled={loadingTrial || progress !== null} />
            )}
            {trial && (
              <CaseReportFinder key={trial.nct_id} nctId={trial.nct_id} chosen={reports} disabled={progress !== null}
                onToggle={(r, on) => setReports(on ? [...reports, r] : reports.filter((x) => x.id !== r.id))} />
            )}
            {loadingTrial && <p className="text-xs text-muted" role="status">Loading the trial…</p>}
            {trialError && <p className="text-xs text-bad" role="alert">{trialError}</p>}
            <fieldset>
              <legend className="mb-1 text-sm">Example case reports</legend>
              <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
                {vignettes.map((v) => (
                  <label key={v.id} className="flex cursor-pointer gap-2 rounded p-1 text-xs hover:bg-subtle">
                    <input
                      type="checkbox"
                      checked={chosen.includes(v.id)}
                      onChange={(e) => setChosen(e.target.checked ? [...chosen, v.id] : chosen.filter((c) => c !== v.id))}
                      className="mt-0.5 accent-[var(--accent)]"
                    />
                    <span>
                      <span className="font-medium">{v.id}</span>
                      {" "}{v.text.slice(0, 80)}…
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div>
              <label htmlFor="pasted" className="mb-1 block text-sm">More patients, one per line</label>
              <textarea id="pasted" rows={3} value={pasted} onChange={(e) => setPasted(e.target.value)} className="w-full rounded-lg border border-line bg-page p-2 text-sm" />
            </div>
            <Button type="submit" className="w-full" disabled={!trial || !trial.criteria.length || count === 0 || progress !== null}>
              {!trial ? "Choose a trial first" : count === 0 ? "Choose patients" : `Screen ${count} ${count === 1 ? "patient" : "patients"}`}
            </Button>
          </form>
        </Card>
        {selected && patients[selected] && (
          <Card className="p-5">
            <h2 className="mb-2 font-semibold">Patient {selected}</h2>
            <div className="max-h-64 overflow-y-auto"><PatientText text={patients[selected]} quote={active?.quote ?? ""} /></div>
            {(() => { const ex = [...vignettes, ...reports].find((v) => v.id === selected && v.source === "published"); return ex ? <div className="mt-2"><Citation example={ex} /></div> : null; })()}
          </Card>
        )}
      </div>

      <div className="min-w-0 space-y-4">
        {trial && <TrialCard key={trial.nct_id} trial={trial} onChange={changeTrial} criteriaOpen={!results && !progress} />}
        {progress && <ProgressBar progress={progress} />}
        {error && <Card className="bg-bad-soft p-5 text-sm text-bad"><p role="alert">{error}</p></Card>}
        {rows.some(([, v]) => v.fallback) && <FallbackNotice checked={rows.filter(([, v]) => v.fallback).length} total={rows.length} />}
        {trial && !progress && !error && results && (
          <Card className="overflow-hidden">
            <div className="border-b border-line px-5 py-3.5">
              <h2 className="font-semibold">Results for {rows.length} {rows.length === 1 ? "patient" : "patients"}</h2>
              <p className="text-xs text-muted">A patient whose record doesn't mention the trial's condition shows “Insufficient data”, not a block.</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr><th scope="col" className="px-5 py-2 font-medium">Patient</th><th scope="col" className="px-2 py-2 font-medium">Verdict</th><th scope="col" className="px-2 py-2 text-right font-medium">Confirmed</th><th scope="col" className="px-2 py-2 text-right font-medium">Blocking</th><th scope="col" className="px-5 py-2 text-right font-medium">Unknown</th></tr>
                </thead>
                <tbody>
                  {rows.map(([name, v]) => (
                    <tr key={name} className={`border-t border-line ${selected === name ? "bg-accent-soft" : "hover:bg-subtle"}`}>
                      <th scope="row" className="px-5 py-2.5 text-left font-medium">
                        <button type="button" aria-pressed={selected === name} className="cursor-pointer underline-offset-2 hover:underline" onClick={() => { setSelected(name); setActive(null); }}>{name}</button>
                      </th>
                      <td className="px-2 py-2.5"><span className="flex flex-wrap gap-1.5"><VerdictPill verdict={v.verdict} />{v.fallback && <RulesPill />}</span></td>
                      <td className="px-2 py-2.5 text-right tabular-nums">{Math.round(v.score * 100)}%</td>
                      <td className="px-2 py-2.5 text-right tabular-nums">{v.blockers.length}</td>
                      <td className="px-5 py-2.5 text-right tabular-nums">{v.missing.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
        {current && <TrialDetail key={selected} verdict={current} activeId={active?.id ?? null} onSelect={(cid, quote) => setActive({ id: cid, quote })} />}
        {!trial && !results && !progress && !error && (
          <Card className="p-8 text-center">
            <h2 className="font-semibold">Screen a group against one trial</h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted">Pick a suggested trial or search for one. You'll see its description and every criterion before anything is checked.</p>
          </Card>
        )}
      </div>
    </div>
  );
}

function sorted(results: Record<string, TrialVerdict>): [string, TrialVerdict][] {
  return Object.entries(results).sort(([, a], [, b]) => ORDER[a.verdict] - ORDER[b.verdict] || b.score - a.score);
}
