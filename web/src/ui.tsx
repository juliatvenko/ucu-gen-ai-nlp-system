import type { ReactNode } from "react";
import { findQuote } from "./api";
import type { Check, Criterion, Progress as ProgressData, Profile, Verdict, Vignette } from "./types";

export const VERDICT: Record<Verdict, { label: string; tone: string; dot: string }> = {
  likely_eligible: { label: "Likely eligible", tone: "bg-good-soft text-good", dot: "bg-good" },
  needs_more_data: { label: "Possible, needs data", tone: "bg-warn-soft text-warn", dot: "bg-warn" },
  insufficient_data: { label: "Insufficient data", tone: "bg-subtle text-muted", dot: "bg-muted" },
  not_eligible: { label: "Not eligible", tone: "bg-bad-soft text-bad", dot: "bg-bad" },
};

export function Pill({ tone, children }: { tone: string; children: ReactNode }) {
  // Long condition names wrap instead of pushing the page sideways.
  return <span className={`inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium [overflow-wrap:anywhere] ${tone}`}>{children}</span>;
}

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const v = VERDICT[verdict];
  return (
    <Pill tone={v.tone}>
      <span className={`h-1.5 w-1.5 rounded-full ${v.dot}`} aria-hidden />
      {v.label}
    </Pill>
  );
}

export function RulesPill() {
  return <Pill tone="bg-warn-soft text-warn">Rules only</Pill>;
}

export function FallbackNotice({ checked, total }: { checked: number; total: number }) {
  const scope = total ? `${checked} of ${total} ${total === 1 ? "trial was" : "trials were"} checked by the rule-based baseline` : "this result came from the rule-based baseline";
  return (
    <Card className="bg-warn-soft p-4 text-sm text-warn">
      <p role="status"><strong className="font-semibold">The model was unavailable, so {scope}.</strong> Rules miss most exclusions and answer “insufficient data” far more often, so treat these as weaker. Try again later for a model check.</p>
    </Card>
  );
}

export function Citation({ example }: { example: Vignette }) {
  return (
    <p className="text-xs text-muted">
      Published case report:{" "}
      <a href={example.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{example.title} ({example.year}), PMID {example.pmid} ↗</a>.{" "}
      Text unchanged, from {example.credit}.
    </p>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-line bg-card ${className}`}>{children}</section>;
}

export function Button({ variant = "primary", className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const look = variant === "primary"
    ? "bg-accent text-accent-ink hover:opacity-90"
    : "border border-line text-ink hover:bg-subtle";
  return <button className={`cursor-pointer rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${look} ${className}`} {...props} />;
}

/** Patient text with the selected quote highlighted and scrolled into view. */
export function PatientText({ text, quote }: { text: string; quote: string }) {
  const range = quote ? findQuote(text, quote) : null;
  if (!range) return <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>;
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {text.slice(0, range[0])}
      <mark ref={(el) => el?.scrollIntoView({ block: "nearest", behavior: "smooth" })}>{text.slice(range[0], range[1])}</mark>
      {text.slice(range[1])}
    </p>
  );
}

export function ProgressBar({ progress }: { progress: ProgressData }) {
  const steps = [
    { key: "profile", label: "Reading the patient description" },
    { key: "search", label: progress.query ? `Searching ClinicalTrials.gov for “${progress.query}”` : "Searching ClinicalTrials.gov" },
    { key: "check", label: progress.total ? `Checking criteria: ${progress.done ?? 0} of ${progress.total} finished` : "Checking criteria" },
  ];
  const current = steps.findIndex((s) => s.key === progress.stage);
  const share = progress.stage === "check" && progress.total ? (progress.done ?? 0) / progress.total : 0;
  return (
    <Card className="p-5" >
      <div role="status" aria-live="polite">
        <ol className="space-y-2.5">
          {steps.map((step, i) => (
            <li key={step.key} className={`flex items-center gap-2.5 text-sm ${i > current ? "text-muted" : ""}`}>
              <span className={`flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] ${i < current ? "bg-accent text-accent-ink" : i === current ? "border-2 border-accent" : "border border-line"}`} aria-hidden>
                {i < current ? "✓" : i === current ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> : ""}
              </span>
              {step.label}
            </li>
          ))}
        </ol>
        {progress.stage === "check" && (
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-subtle">
            <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.max(share * 100, 4)}%` }} />
          </div>
        )}
      </div>
    </Card>
  );
}

function Tags({ title, items, tone = "bg-subtle" }: { title: string; items: string[]; tone?: string }) {
  if (!items.length) return null;
  return (
    <div>
      <dt className="mb-1 text-xs font-medium text-muted">{title}</dt>
      <dd className="flex flex-wrap gap-1.5">
        {items.map((item) => <span key={item} className={`rounded-md px-2 py-0.5 text-xs ${tone}`}>{item}</span>)}
      </dd>
    </div>
  );
}

export function ProfileSummary({ profile }: { profile: Profile }) {
  const basics = [profile.age !== null ? `${profile.age} years` : "", profile.sex ?? ""].filter(Boolean);
  const labs = profile.labs.map((l) => `${l.name} ${l.value}${l.unit ? ` ${l.unit}` : ""}`);
  return (
    <dl className="space-y-3">
      <Tags title="Age and sex" items={basics} />
      <Tags title="Diagnoses" items={profile.diagnoses} tone="bg-accent-soft" />
      <Tags title="Medications" items={profile.medications} />
      <Tags title="Measurements" items={labs} />
      <Tags title="History" items={profile.history} />
      <Tags title="Stated as absent" items={profile.absent} />
    </dl>
  );
}

const STATUS = {
  met: { label: "Met", tone: "bg-good-soft text-good" },
  not_met: { label: "Not met", tone: "bg-bad-soft text-bad" },
  insufficient: { label: "Insufficient data", tone: "bg-subtle text-muted" },
} as const;

/** Why a criterion may not apply to everyone. Parsing decides this; the interface only names it. */
export function structureNote(c: Criterion): string {
  if (c.cohort === "other person") return "About a donor or relative, not the patient";
  if (c.group) return c.group_needed && c.group_needed > 1 ? `One of several options (${c.group_needed} needed)` : "One of several options";
  if (c.conditional) return "Applies to some patients only";
  if (c.cohort) return `For the ${c.cohort} group`;
  return "";
}

export function CriterionRow({ criterion, check, blocks, active, onSelect }: {
  criterion: Criterion;
  check: Check | undefined;
  blocks: boolean;
  active: boolean;
  onSelect: () => void;
}) {
  const status = STATUS[check?.status ?? "insufficient"];
  const clickable = Boolean(check?.evidence);
  const body = (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        {criterion.screening_only ? <Pill tone="bg-subtle text-muted">Confirmed at screening</Pill> : <Pill tone={status.tone}>{status.label}</Pill>}
        {blocks && <Pill tone="bg-bad text-card">Blocks this trial</Pill>}
        {structureNote(criterion) && <Pill tone="bg-subtle text-muted">{structureNote(criterion)}</Pill>}
      </div>
      <p className="mt-1.5 text-sm">{criterion.text}</p>
      {check?.evidence && <p className="mt-1 text-xs text-muted">Quote: “{check.evidence}”</p>}
      {check?.source === "guard" && <p className="mt-1 text-xs text-muted">{check.reasoning}</p>}
    </>
  );
  const frame = `block w-full rounded-lg border p-3 text-left ${active ? "border-accent bg-accent-soft" : "border-line"}`;
  return clickable
    ? <button type="button" onClick={onSelect} aria-pressed={active} className={`${frame} cursor-pointer transition hover:border-accent`}>{body}</button>
    : <div className={frame}>{body}</div>;
}
