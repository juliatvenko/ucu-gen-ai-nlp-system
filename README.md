# TrialMatch

Compares a patient description with clinical-trial eligibility criteria. Each criterion gets **met**, **not met**, or **insufficient data**, with a quote as evidence. Assistive only: clinicians and study staff make the final decision.

**Use synthetic or published data only.** Free LLM endpoints may train on what you send.

- Report: [docs/report.pdf](docs/report.pdf), results in `evals/results/`
- Diagrams and components: [docs/architecture.md](docs/architecture.md)
- CRISP-DM log: [docs/crisp_dm.md](docs/crisp_dm.md)
- Agent instructions: [AGENTS.md](AGENTS.md)

## Setup

Needs Python 3.11 or newer.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

## Run the app

```bash
.venv/bin/python -m uvicorn server:app --port 8000
```

Then open http://localhost:8000. The built interface is in `web/dist`, so this needs no Node. With no key, it runs in **offline mode**: a rule-based baseline that abstains often. If the model is unavailable during a check, those results also use the rules and are labelled "Rules only".

To change the interface, you need Node. Run the API command above, then:

```bash
npm --prefix web install
```

```bash
npm --prefix web run dev
```

Build with `npm --prefix web run build` when you're done.

## Add a model

```bash
cp .env.example .env
```

Then set one provider in `.env`. The reported results use the first.

- **Google AI Studio, free.** Create a key in [AI Studio](https://aistudio.google.com), then set:
  ```
  LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
  LLM_API_KEY=your-key
  LLM_MODEL=gemini-3.5-flash-lite
  LLM_RPM=14
  ```
  Google may use free-tier content and humans may read it.
- `OPENROUTER_API_KEY`: free models, at 50 requests a day without credits. Set `LLM_MODEL` to one specific model before running evals.
- `ANTHROPIC_API_KEY`: paid. Defaults to `claude-opus-5-5`, with server-side refusal fallback on. Set `LLM_MODEL` for a cheaper model.

## Evals

Download the datasets once (about 8 MB, including the first 5 MB of PMC-Patients), then build the gazetteer:

```bash
.venv/bin/python -m scripts.download_data
```

```bash
.venv/bin/python -m scripts.chia
```

To rebuild the five published demo cases in `data/pmc_examples.json`:

```bash
.venv/bin/python -m scripts.pmc_examples
```

Offline, free:

```bash
.venv/bin/python -m evals.run_all --mode offline --split test
```

LLM mode uses your quota or money. Start small, since each patient or trial is one or more calls. If you hit a daily limit, the run stops with a message and resumes from the cache next time:

```bash
.venv/bin/python -m evals.run_all --mode llm --split dev --only checker --limit 2
```

A wider run, once the small one looks right:

```bash
.venv/bin/python -m evals.run_all --mode llm --split test --only profile checker safety
```

```bash
.venv/bin/python -m evals.run_all --mode llm --split test --only parsing trec retrieval
```

Rebuild the report tables:

```bash
.venv/bin/python -m evals.build_report
```

Model responses are cached in `.cache/llm`, so repeat runs are free.

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Trace one input through every component

```bash
.venv/bin/python -m scripts.trace_input --vignette d01
```

The interface also has a Trace button, and every step is logged to `traces/`.

## Layout

```
server.py           FastAPI: API and the built interface
web/                React interface (source in web/src, build in web/dist)
trialmatch/         Pipeline, one module per component
evals/              One eval per component, results in evals/results/
data/               Gold data. Raw downloads go in data/raw/ (not committed)
scripts/            Data download, gazetteer, tracing
docs/               Report, architecture, CRISP-DM log, reflection
.claude/skills/     Skills for the agentic workflow
AGENTS.md           Instructions for coding agents
```
