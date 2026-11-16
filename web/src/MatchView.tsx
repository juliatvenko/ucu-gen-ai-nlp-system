import { useRef, useState } from "react";
import { postStream } from "./api";
import { TrialDetail } from "./TrialDetail";
import type { MatchResult, Progress, Vignette } from "./types";
import { Button, Card, Citation, FallbackNotice, PatientText, ProfileSummary, ProgressBar, RulesPill, VerdictPill } from "./ui";

const NOTICE = {
  urgent: "bg-bad-soft text-bad",
  refuse: "bg-warn-soft text-warn",
  ask_diagnosis: "bg-accent-soft text-ink",
  proceed: "",
};

export function MatchView({ vignettes }: { vignettes: Vignette[] }) {
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(true);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [active, setActive] = useState<{ id: string; quote: string } | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState("");
  const controller = useRef<AbortController | null>(null);

  async function run(input: string) {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setText(input);
    setEditing(false);
    setError("");
    setResult(null);
    setActive(null);
    setAnswers({});
    setExtra("");
    setProgress({ stage: "profile" });
    try {
      await postStream("/api/match", { text: input }, (event, data) => {
        if (event === "stage") setProgress(data);
        if (event === "result") {
          const r: MatchResult = data.result;
          setResult(r);
          setSelected(r.verdicts[0]?.trial.nct_id ?? null);
          if (r.safety.action !== "proceed") setEditing(true);
        }
      }, abort.signal);
    } catch (e) {
      if (abort.signal.aborted) return;
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setEditing(true);
    }
    if (!abort.signal.aborted) setProgress(null);
  }

  function recheck() {
    const lines = Object.entries(answers)
      .filter(([, a]) => a.trim())
      .map(([q, a]) => `Follow-up: ${q} ${a.trim()}`);
    if (extra.trim()) lines.push(extra.trim());
    if (lines.length) run(`${text}\n${lines.join("\n")}`);
  }

  const running = progress !== null;
  const hasAnswer = extra.trim() || Object.values(answers).some((a) => a.trim());
  const current = result?.verdicts.find((v) => v.trial.nct_id === selected);
  // Credit stays visible after follow-up answers are appended, since the case text is still there.
  const published = vignettes.find((v) => v.source === "published" && text.trim().startsWith(v.text.trim()));

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(320px,400px)_minmax(0,1fr)]">
      <div className="space-y-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
        <Card className="p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">Patient</h2>
            {!editing && !running && <Button variant="ghost" className="!px-2.5 !py-1 !text-xs" onClick={() => setEditing(true)}>Edit</Button>}
          </div>
          {editing ? (
            <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) run(text.trim()); }}>
              <label htmlFor="patient" className="block text-sm text-muted">Diagnosis, age, sex, treatments, and recent labs.</label>
              <textarea
                id="patient"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={8}
                placeholder="58-year-old woman with type 2 diabetes on metformin. HbA1c 8.4%…"
                className="w-full resize-y rounded-lg border border-line bg-page p-3 text-sm placeholder:text-muted"
              />
              <div>
                <label htmlFor="example" className="mb-1 block text-xs font-medium text-muted">Or use an example</label>
                <select
                  id="example"
                  value=""
                  onChange={(e) => { const v = vignettes.find((x) => x.id === e.target.value); if (v) setText(v.text); }}
                  className="w-full rounded-lg border border-line bg-page p-2 text-sm"
                >
                  <option value="">Choose a published case report</option>
                  {vignettes.map((v) => <option key={v.id} value={v.id}>{v.text.slice(0, 70)}…</option>)}
                </select>
              </div>
              {published && <Citation example={published} />}
              <Button type="submit" className="w-full" disabled={!text.trim()}>Find trials</Button>
            </form>
          ) : (
            <div className="mt-3 space-y-2">
              <div className="max-h-72 overflow-y-auto"><PatientText text={text} quote={active?.quote ?? ""} /></div>
              {published && <Citation example={published} />}
            </div>
          )}
        </Card>

        {result?.profile && result.safety.action === "proceed" && (
          <Card className="p-5">
            <h2 className="mb-3 font-semibold">What was extracted</h2>
            <ProfileSummary profile={result.profile} />
          </Card>
        )}

        {result && result.questions.length > 0 && (
          <Card className="p-5">
            <h2 className="font-semibold">Answers that would help most</h2>
            <p className="mt-1 text-xs text-muted">These settle the most open criteria. Skip any you don't know.</p>
            <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); recheck(); }}>
              {result.questions.map((q) => (
                <div key={q}>
                  <label htmlFor={q} className="mb-1 block text-sm">{q}</label>
                  <input id={q} value={answers[q] ?? ""} onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })} className="w-full rounded-lg border border-line bg-page px-3 py-2 text-sm" />
                </div>
              ))}
              <div>
                <label htmlFor="extra" className="mb-1 block text-sm">Anything else to add?</label>
                <input id="extra" value={extra} onChange={(e) => setExtra(e.target.value)} className="w-full rounded-lg border border-line bg-page px-3 py-2 text-sm" />
              </div>
              <Button type="submit" variant="ghost" className="w-full" disabled={!hasAnswer}>Add answers and re-check</Button>
            </form>
          </Card>
        )}
      </div>

      <div className="min-w-0 space-y-4">
        {running && progress && <ProgressBar progress={progress} />}
        {error && <Card className="bg-bad-soft p-5 text-sm text-bad"><p role="alert">{error}</p></Card>}
        {result?.fallback && <FallbackNotice checked={result.verdicts.filter((v) => v.fallback).length} total={result.verdicts.length} />}
        {result && result.safety.action !== "proceed" && (
          <Card className={`p-5 text-sm ${NOTICE[result.safety.action]}`}><p role="alert">{result.safety.message}</p></Card>
        )}
        {result?.note && <Card className="p-5 text-sm">{result.note}</Card>}

        {result && result.verdicts.length > 0 && (
          <>
            <Card className="overflow-hidden">
              <div className="border-b border-line px-5 py-3.5">
                <h2 className="font-semibold">Top {result.verdicts.length} of {result.candidates} trials for “{result.query}”</h2>
              </div>
              <ul>
                {result.verdicts.map((v) => {
                  const isSelected = v.trial.nct_id === selected;
                  return (
                    <li key={v.trial.nct_id} className="border-b border-line last:border-0">
                      <button
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => { setSelected(v.trial.nct_id); setActive(null); }}
                        className={`grid w-full cursor-pointer gap-x-4 gap-y-1.5 px-5 py-3 text-left transition sm:grid-cols-[minmax(0,1fr)_auto] ${isSelected ? "bg-accent-soft" : "hover:bg-subtle"}`}
                      >
                        <span className="min-w-0 text-sm font-medium leading-snug">{v.trial.title}</span>
                        <span className="flex flex-wrap gap-1.5 sm:justify-self-end">{v.fallback && <RulesPill />}<VerdictPill verdict={v.verdict} /></span>
                        <span className="text-xs text-muted sm:col-span-2">
                          {v.trial.nct_id} · {Math.round(v.score * 100)}% of checkable criteria confirmed · {v.blockers.length} blocking · {v.missing.length} unknown
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Card>
            {current && <TrialDetail key={current.trial.nct_id} verdict={current} activeId={active?.id ?? null} onSelect={(id, quote) => setActive({ id, quote })} />}
          </>
        )}

        {!result && !running && !error && (
          <Card className="p-8 text-center">
            <h2 className="font-semibold">Results appear here</h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted">Each criterion gets a status and a quote from the patient description, or an honest “insufficient data”.</p>
          </Card>
        )}
      </div>
    </div>
  );
}
