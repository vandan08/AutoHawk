from __future__ import annotations

import shutil
from pathlib import Path

import requests
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .db import Database
from .llm import get_provider
from .profile import Profile
from .report import write_report
from .scoring import LLMScorer, keyword_score
from .sources import fetch_all
from .tailor import generate_cover_letter
from .utils import title_matches

load_dotenv()

app = typer.Typer(
    name="autohawk",
    help="Job aggregation, AI fit-scoring, and cover-letter tailoring — one place for your whole job hunt.",
    no_args_is_help=True,
)
console = Console()

PROFILE_OPT = typer.Option("profile.yaml", "--profile", "-p", help="Path to your profile YAML")


@app.command()
def init() -> None:
    """Create profile.yaml from the bundled template."""
    target = Path("profile.yaml")
    if target.exists():
        console.print("[yellow]profile.yaml already exists — not overwriting.[/]")
        raise typer.Exit(1)
    template = Path(__file__).resolve().parent.parent / "profile.example.yaml"
    if not template.exists():  # installed via pip rather than cloned
        template = Path("profile.example.yaml")
    shutil.copyfile(template, target)
    console.print("[green]Created profile.yaml[/] — edit it, then run [bold]autohawk fetch[/].")


@app.command()
def fetch(profile_path: str = PROFILE_OPT) -> None:
    """Pull jobs from every configured source into the local database."""
    profile = Profile.load(profile_path)
    db = Database()
    results = fetch_all(profile.sources)
    keywords = profile.title_keywords
    total_new = 0
    for source, outcome in results.items():
        if isinstance(outcome, Exception):
            console.print(f"[red]{source}[/]: failed — {outcome}")
            continue
        new = sum(
            db.upsert_job(job)
            for job in outcome
            if job.url and title_matches(job.title, keywords)
        )
        total_new += new
        console.print(f"[cyan]{source}[/]: {len(outcome)} fetched, [green]{new} new[/] after title filter")
    counts = db.counts()
    console.print(
        f"\nDone. [bold]{total_new}[/] new jobs saved "
        f"({counts['total']} total, {counts['unscored']} awaiting scoring)."
    )


@app.command()
def score(
    profile_path: str = PROFILE_OPT,
    limit: int = typer.Option(0, "--limit", "-n", help="Score at most N jobs (0 = all unscored)"),
    keyword_only: bool = typer.Option(False, "--keyword-only", help="Skip the LLM, use keyword overlap"),
) -> None:
    """Score unscored jobs against your profile (Claude, or keyword fallback)."""
    profile = Profile.load(profile_path)
    db = Database()
    jobs = db.unscored_jobs(limit or None)
    if not jobs:
        console.print("Nothing to score — run [bold]autohawk fetch[/] first.")
        return

    provider = None
    if not keyword_only:
        try:
            provider = get_provider()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)
        if provider is None:
            console.print(
                "[yellow]No LLM available (no ANTHROPIC_API_KEY, Ollama not running) — "
                "using keyword scoring. See DEPLOYMENT.md for Ollama setup.[/]"
            )
        else:
            console.print(f"Scoring with [cyan]{provider.describe()}[/]")
    scorer = LLMScorer(profile, provider) if provider else None

    scored = failed = 0
    with console.status(f"Scoring {len(jobs)} jobs...") as status:
        for i, row in enumerate(jobs, 1):
            status.update(f"[{i}/{len(jobs)}] {row['title']} @ {row['company']}")
            try:
                if scorer:
                    r = scorer.score(row["title"], row["company"], row["location"], row["description"])
                    db.save_score(
                        row["id"], r.score, "llm", r.recommendation,
                        r.matched_skills, r.gaps, r.reasoning,
                    )
                else:
                    pts, matched = keyword_score(profile.skills, row["title"], row["description"])
                    db.save_score(row["id"], pts, "keyword", matched_skills=matched)
                scored += 1
            except requests.exceptions.ConnectionError:
                console.print("[red]Lost connection to the LLM backend — stopping. Re-run to resume.[/]")
                break
            except Exception as exc:
                if type(exc).__name__ == "RateLimitError":
                    console.print("[red]Rate limited by the API — stopping. Re-run to resume.[/]")
                    break
                console.print(f"[red]Failed on {row['id']}[/]: {exc}")
                failed += 1
    console.print(f"\nScored [green]{scored}[/] jobs" + (f", [red]{failed} failed[/]" if failed else "") + ".")
    console.print("View the ranking with [bold]autohawk shortlist[/].")


@app.command()
def shortlist(
    limit: int = typer.Option(20, "--limit", "-n"),
    min_score: int = typer.Option(0, "--min-score", "-m"),
) -> None:
    """Show the top-ranked jobs."""
    db = Database()
    rows = db.shortlist(limit=limit, min_score=min_score)
    if not rows:
        console.print("No scored jobs yet — run [bold]autohawk score[/].")
        return
    table = Table(title=f"Top {len(rows)} matches", show_lines=False)
    table.add_column("Score", justify="right", style="bold yellow")
    table.add_column("Rec", style="cyan")
    table.add_column("Title", style="bold", max_width=42, overflow="ellipsis")
    table.add_column("Company", max_width=20, overflow="ellipsis")
    table.add_column("Location", max_width=22, overflow="ellipsis")
    table.add_column("ID", style="dim")
    for r in rows:
        table.add_row(
            str(r["score"]), r["recommendation"] or "-", r["title"],
            r["company"], r["location"] or "-", r["id"],
        )
    console.print(table)
    console.print("\nDetails: [bold]autohawk show <ID>[/] · Letter: [bold]autohawk letter <ID>[/]")


@app.command()
def show(job_id: str) -> None:
    """Show full details and scoring rationale for one job."""
    db = Database()
    r = db.get_job(job_id)
    if r is None:
        console.print(f"[red]No job with id {job_id}[/]")
        raise typer.Exit(1)
    console.print(f"\n[bold]{r['title']}[/] @ [cyan]{r['company']}[/]  ({r['location'] or 'n/a'})")
    console.print(f"[dim]{r['url']}[/]")
    console.print(f"Source: {r['source']} · Posted: {r['posted_at'] or '?'} · Status: {r['status']}")
    if r["score"] is not None:
        console.print(f"\nScore: [bold yellow]{r['score']}[/] ({r['score_method']}) — {r['recommendation'] or ''}")
        if r["matched_skills"]:
            console.print(f"Matched: [green]{r['matched_skills']}[/]")
        if r["gaps"]:
            console.print(f"Gaps: [red]{r['gaps']}[/]")
        if r["reasoning"]:
            console.print(f"\n{r['reasoning']}")
    console.print(f"\n[dim]{(r['description'] or '')[:1200]}[/]\n")


@app.command()
def letter(
    job_id: str,
    profile_path: str = PROFILE_OPT,
    out_dir: str = typer.Option("letters", "--out", help="Directory to save the letter"),
) -> None:
    """Generate a tailored cover letter for a job."""
    try:
        provider = get_provider()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    if provider is None:
        console.print(
            "[red]Cover letters need an LLM. Set ANTHROPIC_API_KEY, or install and "
            "run Ollama (see DEPLOYMENT.md).[/]"
        )
        raise typer.Exit(1)
    db = Database()
    r = db.get_job(job_id)
    if r is None:
        console.print(f"[red]No job with id {job_id}[/]")
        raise typer.Exit(1)
    profile = Profile.load(profile_path)
    console.print(f"Using [cyan]{provider.describe()}[/]")
    with console.status(f"Writing letter for {r['title']} @ {r['company']}..."):
        text = generate_cover_letter(profile, r["title"], r["company"], r["description"], provider)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_company = "".join(c if c.isalnum() or c in "-_" else "_" for c in r["company"])[:40]
    path = out / f"{job_id}_{safe_company}.txt"
    path.write_text(text, encoding="utf-8")
    console.print(f"\n{text}\n")
    console.print(f"[green]Saved to {path}[/]")


@app.command()
def report(
    limit: int = typer.Option(30, "--limit", "-n"),
    min_score: int = typer.Option(0, "--min-score", "-m"),
) -> None:
    """Generate a standalone HTML shortlist report."""
    db = Database()
    rows = db.shortlist(limit=limit, min_score=min_score)
    path = write_report(rows)
    console.print(f"[green]Report written to {path}[/] — open it in your browser.")


@app.command()
def mark(
    job_id: str,
    status: str = typer.Argument(..., help="applied | shortlisted | rejected | archived"),
) -> None:
    """Track your pipeline: mark a job applied / shortlisted / rejected / archived."""
    valid = {"applied", "shortlisted", "rejected", "archived", "new"}
    if status not in valid:
        console.print(f"[red]Status must be one of: {', '.join(sorted(valid))}[/]")
        raise typer.Exit(1)
    db = Database()
    if db.get_job(job_id) is None:
        console.print(f"[red]No job with id {job_id}[/]")
        raise typer.Exit(1)
    db.set_status(job_id, status)
    console.print(f"[green]{job_id} -> {status}[/]")


@app.command()
def digest(
    hours: int = typer.Option(24, "--hours", help="Look back this many hours of fetches"),
    limit: int = typer.Option(5, "--limit", "-n"),
    min_score: int = typer.Option(60, "--min-score", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print instead of emailing"),
) -> None:
    """Email (or print) the top new matches — pair with cron for a daily digest."""
    from datetime import datetime, timedelta, timezone

    from .digest import build_digest, send_email, smtp_configured

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = Database().recent_scored(since, min_score=min_score, limit=limit)
    if not rows:
        console.print(f"No new matches scoring ≥{min_score} in the last {hours}h — nothing to send.")
        return
    subject, text_body, html_body = build_digest(rows)
    if dry_run or not smtp_configured():
        if not dry_run:
            console.print(
                "[yellow]SMTP not configured (AUTOHAWK_SMTP_HOST / AUTOHAWK_DIGEST_TO) — "
                "printing instead.[/]\n"
            )
        console.print(f"[bold]{subject}[/]\n\n{text_body}")
        return
    to_addr = send_email(subject, text_body, html_body)
    console.print(f"[green]Digest with {len(rows)} match(es) sent to {to_addr}[/]")


@app.command()
def web(
    profile_path: str = PROFILE_OPT,
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8090, "--port"),
) -> None:
    """Run the local web dashboard (browse, score, letters — no CLI needed)."""
    from .web import serve

    console.print(f"AutoHawk dashboard on [bold cyan]http://{host}:{port}[/] — Ctrl+C to stop.")
    try:
        serve(host, port, profile_path)
    except KeyboardInterrupt:
        console.print("\nStopped.")


@app.command()
def status() -> None:
    """Pipeline overview."""
    counts = Database().counts()
    console.print(
        f"Jobs: [bold]{counts['total']}[/] total · {counts['scored']} scored · "
        f"{counts['unscored']} unscored · [green]{counts['applied']} applied[/]"
    )


if __name__ == "__main__":
    app()
