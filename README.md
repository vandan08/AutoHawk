# AutoHawk 🦅

**Your whole job hunt from one place** — aggregate jobs from across the internet, score them against your profile with Claude, and generate tailored cover letters. You keep the final click on "submit"; AutoHawk automates everything before it.

```
 sources                  pipeline                        you
┌────────────┐
│ Greenhouse │─┐
│ Lever      │ │   ┌───────┐   ┌────────┐   ┌───────────┐   ┌────────┐
│ RemoteOK   │ ├──▶│ fetch │──▶│ score  │──▶│ shortlist │──▶│ letter │──▶ apply
│ Remotive   │ │   └───────┘   └────────┘   └───────────┘   └────────┘
│ Adzuna     │─┘    SQLite      Ollama /      ranked CLI      tailored
└────────────┘      dedupe      Claude /      + HTML report   cover letter
                                keywords
```

**Runs 100% free**: AI scoring works with a local [Ollama](https://ollama.com) model (no account, no API key, fully private), with hosted Claude as an optional upgrade and keyword matching as the zero-setup floor.

## Why not a full auto-apply bot?

Platforms like LinkedIn and Indeed prohibit automated applying and ban accounts for it, and mass-fired generic applications get filtered by recruiters anyway. AutoHawk automates the 90% that's safe and high-leverage — discovery, deduplication, fit-ranking, and tailoring — and leaves the submit to you.

## Quickstart

```bash
git clone https://github.com/vandan08/AutoHawk.git
cd AutoHawk
pip install -e .

# 1. Set up your profile (gitignored — never leaves your machine)
autohawk init
#    → edit profile.yaml: skills, experience, target roles, sources

# 2. Optional but recommended: AI scoring + cover letters (pick one)
#    a) FREE, local:  install Ollama from https://ollama.com, then:
ollama pull llama3.1:8b
#    b) hosted Claude: copy .env.example .env and set ANTHROPIC_API_KEY
#    (with neither, scoring falls back to keyword matching)

# 3. Run the pipeline
autohawk fetch        # pull jobs from all configured sources
autohawk score        # score each job 0-100 against your profile
autohawk shortlist    # ranked table in your terminal
autohawk report       # standalone HTML report in reports/
```

## Commands

| Command | What it does |
|---|---|
| `autohawk init` | Create `profile.yaml` from the template |
| `autohawk fetch` | Pull jobs from all configured sources into SQLite (deduped by URL) |
| `autohawk score [-n N] [--keyword-only]` | Score unscored jobs; Claude with structured output, or keyword overlap fallback |
| `autohawk shortlist [-n 20] [-m 60]` | Ranked table of top matches |
| `autohawk show <id>` | Full posting + scoring rationale (matched skills, gaps) |
| `autohawk letter <id>` | Generate a tailored ≤250-word cover letter into `letters/` |
| `autohawk report` | Standalone HTML shortlist report |
| `autohawk mark <id> applied` | Track your pipeline (applied / shortlisted / rejected / archived) |
| `autohawk status` | Pipeline counts |

## Job sources

| Source | Auth | Config |
|---|---|---|
| **Greenhouse** | none | list of company board slugs (`boards.greenhouse.io/<slug>`) |
| **Lever** | none | list of company slugs (`jobs.lever.co/<slug>`) |
| **RemoteOK** | none | optional tag filter |
| **Remotive** | none | optional search query |
| **Adzuna** | free API keys | country + search query |

Adding a source is one file in `autohawk/sources/` implementing `fetch(config) -> list[Job]` plus a registry entry — PRs welcome.

## How scoring works

Three providers behind one interface, resolved by `AUTOHAWK_PROVIDER` (default `auto`: Claude if a key is set → Ollama if running → keyword fallback):

| Provider | Cost | Setup | Quality |
|---|---|---|---|
| **Ollama** (local) | free | install + `ollama pull llama3.1:8b` | good |
| **Anthropic** (hosted Claude) | pay-per-use | `ANTHROPIC_API_KEY` in `.env` | best |
| **Keyword** (fallback) | free | nothing | basic |

Each job is evaluated against your full profile using **structured outputs** (Claude via `messages.parse`, Ollama via its JSON-schema `format` parameter), returning a validated result:

```json
{
  "score": 82,
  "recommendation": "strong_apply",
  "matched_skills": ["Kubernetes", "Terraform", "CI/CD"],
  "gaps": ["5+ years experience required"],
  "reasoning": "Strong stack overlap with the platform team's needs..."
}
```

On the Claude path, the profile lives in a cached system-prompt prefix, so scoring 100 jobs reuses the cache instead of re-paying for your profile on every call.

## Deployment

Want it running daily on a server (or your own machine) without babysitting? **[DEPLOYMENT.md](DEPLOYMENT.md)** covers local Ollama setup, a full Ubuntu VPS walkthrough (systemd timer, nginx report serving, security checklist), and a one-command Docker Compose stack (`docker compose up -d`).

## Project layout

```
autohawk/
├── cli.py            # Typer CLI — the entry point
├── llm.py            # provider abstraction: Anthropic / Ollama / none
├── db.py             # SQLite storage + shortlist queries
├── profile.py        # profile.yaml loader + prompt rendering
├── sources/          # one fetcher per job board
├── scoring/          # llm.py (structured-output scoring) + keyword.py (fallback)
├── tailor/           # cover-letter generation
└── report/           # standalone HTML report
Dockerfile, docker-compose.yml, docker/   # containerized deployment
DEPLOYMENT.md                             # local / VPS / Docker guides
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests cover the parsers, scorer, and database with captured API fixtures — no network or API key needed.

## Roadmap

- [ ] Email digest (daily cron → top 5 new matches)
- [ ] Hacker News "Who's Hiring" source
- [ ] Resume tailoring per job (not just cover letters)
- [ ] Browser-assisted form prefill (Playwright, human-in-the-loop submit)

## License

MIT
