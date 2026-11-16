# Working with the coding agent

The first section is a factual record of the build session. The reflection itself is for the author to write, since the brief asks you to reflect on this yourself.

## What happened in the session

**Steering files written before the code:** `AGENTS.md` (process, eval rules, system invariants), `CLAUDE.md`, and three skills.

**What context the agent had:** the course brief (PDF), the author's planning notes (`genai-assignment-1.md`) with the topic and data decisions, and memory notes.

**Problems found during the build, and what found them:**

| Problem | Found by |
|---|---|
| "18 years or older" abstained, because "or" counted as complex | Unit test |
| Chia offsets shifted by newline handling, which corrupted the eval and gazetteer | A score that looked implausible |
| TREC recall near zero, largely a flaw in the metric | A score that looked implausible |
| Merged NCT IDs crashed the eval | Running on the test split |
| Only the first bound checked in "≥ 21 and ≤ 65" | Tracing a live trial |
| 40-criteria cap hid later exclusions | Tracing a live trial |
| Two false blockers on real trials, and follow-ups asking about stated facts | Inspecting verdicts on live trials |

A fix also caused a new problem: the larger gazetteer turned "no known allergies" into a diagnosis, caught by rerunning the safety eval.

Real model runs found what fake tests couldn't: malformed JSON repeated by the retry, a free model inventing decisions with real but irrelevant quotes, and a daily quota. The browser found a running server keeping old settings.

The agent also made one false statement: it said it had saved the Nemotron results before it had. It corrected this and copied them in the next turn.

Using the React interface in a browser exposed model instability: one unrelated answer changed 23 of 71 statuses on a trial. No eval measures this.

The author overruled the agent's fix for provider overload. The agent had improved the error message, and the author asked to fall back to the rule-based system instead. A test then caught fallback results missing their "Rules only" label.

**Agent decisions you should know about and can overrule:**
- Used TREC 2021 human judgements (qrels) as an end-to-end eval. Your notes listed only the topics, as an option for vignettes.
- Wrote the gold labels itself, though your notes said you would write or generate them.
- Recommended Gemini over a higher-scoring dev model, for quota and reliability.
- Kept a rule fix that lowered the dev score, because it removed wrong blocks on real trials.

## Your reflection

To write yourself. Questions the brief points at:

1. What did you put in the agent's context, and what did you deliberately leave out?
2. Which rule in `AGENTS.md` changed the result most? Which did nothing?
3. Where did you overrule or correct the agent?
4. What would you change in the steering files next time?
5. Could you explain every component without the agent? Which one was hardest?
