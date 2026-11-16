import { useEffect, useState } from "react";
import { getJson } from "./api";
import { CohortView } from "./CohortView";
import { MatchView } from "./MatchView";
import type { AppStatus, TraceEvent, Vignette } from "./types";
import { Button, Card } from "./ui";

type Tab = "match" | "cohort";

function initialDark(): boolean {
  try {
    const saved = localStorage.getItem("theme");
    if (saved) return saved === "dark";
  } catch { /* storage can be blocked */ }
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

function Trace({ onClose }: { onClose: () => void }) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  useEffect(() => {
    const load = () => getJson<TraceEvent[]>("/api/trace?limit=100").then(setEvents).catch(() => {});
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, []);
  const kindLabel: Record<string, string> = { model: "Model call", tool: "External tool", code: "Plain code" };
  return (
    <Card className="mt-5 p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">Pipeline trace</h2>
        <Button variant="ghost" className="!px-2.5 !py-1 !text-xs" onClick={onClose}>Close</Button>
      </div>
      {!events.length && <p className="mt-2 text-sm text-muted">Nothing yet. Run a check to see each step.</p>}
      <ol className="mt-3 space-y-1.5">
        {[...events].reverse().map((e, i) => (
          <li key={`${e.ts}-${i}`}>
            <details className="rounded-lg border border-line px-3 py-2 text-xs">
              <summary className="cursor-pointer">
                <span className="font-medium">{e.component}</span> · {kindLabel[e.kind] ?? e.kind}
                {e.cached === true ? " · cached" : ""}{typeof e.latency_s === "number" ? ` · ${e.latency_s}s` : ""}{e.error ? " · error" : ""}
              </summary>
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-muted">{JSON.stringify(e, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("match");
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [vignettes, setVignettes] = useState<Vignette[]>([]);
  const [dark, setDark] = useState(initialDark);
  const [showTrace, setShowTrace] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    getJson<AppStatus>("/api/status").then(setStatus).catch(() => setLoadError("Can't reach the TrialMatch server. Is it running?"));
    getJson<Vignette[]>("/api/examples").then(setVignettes).catch(() => setLoadError("Couldn't load the example patients. If you just updated the app, restart the server."));
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* storage can be blocked */ }
  }, [dark]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "match", label: "Find trials for a patient" },
    { key: "cohort", label: "Screen patients for a trial" },
  ];

  return (
    <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-ink" aria-hidden>✓</span>
          <div>
            <h1 className="text-lg font-semibold leading-tight">TrialMatch</h1>
            <p className="text-xs text-muted">Clinical-trial eligibility, with evidence for every decision</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status && (
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${status.mode === "model" ? "bg-accent-soft" : "bg-warn-soft text-warn"}`}>
              {status.mode === "model" ? `Model: ${status.model}` : "Offline mode: rules only, abstains often"}
            </span>
          )}
          <Button variant="ghost" className="!px-2.5 !py-1 !text-xs" aria-pressed={showTrace} onClick={() => setShowTrace(!showTrace)}>Trace</Button>
          <Button variant="ghost" className="!px-2.5 !py-1 !text-xs" onClick={() => setDark(!dark)}>{dark ? "Light" : "Dark"}</Button>
        </div>
      </header>

      <p className="mt-4 rounded-lg bg-warn-soft px-3.5 py-2 text-xs text-warn">
        <strong className="font-semibold">Synthetic or published data only.</strong> Text is sent to an outside model provider, so don't enter private patient data. This is an assistive tool and not medical advice: clinicians and study staff make the final decision.
      </p>
      {loadError && <p role="alert" className="mt-3 rounded-lg bg-bad-soft px-3.5 py-2 text-sm text-bad">{loadError}</p>}

      <nav className="mt-4 flex gap-1 border-b border-line" aria-label="Mode">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-current={tab === t.key ? "page" : undefined}
            onClick={() => setTab(t.key)}
            className={`-mb-px cursor-pointer border-b-2 px-3 py-2 text-sm font-medium transition ${tab === t.key ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="mt-5">
        {/* Both stay mounted, so switching tabs doesn't lose work. */}
        <div hidden={tab !== "match"}><MatchView vignettes={vignettes} /></div>
        <div hidden={tab !== "cohort"}><CohortView vignettes={vignettes} /></div>
        {showTrace && <Trace onClose={() => setShowTrace(false)} />}
      </main>
    </div>
  );
}
