"""Local web dashboard — browse, act on, and refresh your pipeline from a browser.

Standard library only (http.server), so `autohawk web` works on any install
with zero extra dependencies. Binds to localhost by default: this is a
single-user dashboard over your local database, not a multi-tenant app.
"""

from __future__ import annotations

import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .db import Database
from .llm import get_provider
from .profile import Profile
from .scoring import LLMScorer, keyword_score
from .sources import fetch_all
from .tailor import generate_cover_letter
from .utils import title_matches

VALID_STATUSES = ("new", "scored", "shortlisted", "applied", "rejected", "archived")

_STYLE = """
  :root { --bg:#fdfcf9; --fg:#1c1917; --muted:#78716c; --card:#ffffff; --line:#e7e5e4;
          --accent:#b45309; --green:#15803d; --red:#b91c1c; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#131110; --fg:#e7e5e4; --muted:#a8a29e; --card:#1e1b19; --line:#312d2a;
            --accent:#f59e0b; --green:#4ade80; --red:#f87171; }
  }
  * { box-sizing:border-box; }
  body { margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
         font:16px/1.55 Georgia, 'Times New Roman', serif; }
  main { max-width:900px; margin:0 auto; }
  h1 { font-size:1.7rem; margin:0 0 .2rem; } h1 a { color:var(--fg); text-decoration:none; }
  .sub { color:var(--muted); margin:0 0 1.4rem; }
  a { color:var(--accent); }
  table { width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  th, td { text-align:left; padding:.5rem .7rem; border-bottom:1px solid var(--line);
           font-size:.95rem; vertical-align:top; }
  th { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; }
  tr:last-child td { border-bottom:none; }
  .score { font-weight:bold; color:var(--accent); font-size:1.05rem; white-space:nowrap; }
  .badge { display:inline-block; font-size:.72rem; letter-spacing:.04em; text-transform:uppercase;
           border:1px solid var(--line); color:var(--muted); border-radius:999px; padding:.06rem .55rem; }
  .badge.applied { border-color:var(--green); color:var(--green); }
  .badge.rejected, .badge.archived { border-color:var(--red); color:var(--red); }
  .badge.shortlisted, .badge.rec { border-color:var(--accent); color:var(--accent); }
  .bar { display:flex; gap:.7rem; align-items:center; flex-wrap:wrap; margin-bottom:1.2rem; }
  button, input[type=submit] { font:inherit; font-size:.9rem; cursor:pointer; border-radius:8px;
           border:1px solid var(--accent); background:var(--accent); color:#fff; padding:.35rem .9rem; }
  button.ghost { background:transparent; color:var(--accent); }
  input[type=number], select { font:inherit; font-size:.9rem; padding:.3rem .5rem;
           border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--fg); }
  .banner { border:1px solid var(--accent); border-radius:10px; padding:.6rem 1rem;
            margin-bottom:1.2rem; background:var(--card); }
  .error { border-color:var(--red); color:var(--red); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:1.1rem 1.3rem; margin-bottom:1rem; }
  .desc, .letter { white-space:pre-wrap; font-size:.95rem; }
  .meta { color:var(--muted); font-size:.92rem; }
  .actions form { display:inline; }
"""

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{style}</style>
</head>
<body>
<main>
<h1><a href="/">AutoHawk</a></h1>
<p class="sub">{subtitle}</p>
{body}
</main>
{script}
</body>
</html>
"""

_POLL_SCRIPT = """<script>
const poll = setInterval(async () => {
  try {
    const s = await (await fetch('/api/progress')).json();
    const el = document.getElementById('worker-msg');
    if (el) el.textContent = s.message;
    if (!s.running) { clearInterval(poll); location.reload(); }
  } catch (e) { /* server restarting; keep polling */ }
}, 2000);
</script>"""


def _e(value) -> str:
    return html.escape(str(value or ""))


def _page(title: str, subtitle: str, body: str, script: str = "") -> str:
    return _PAGE.format(title=_e(title), style=_STYLE, subtitle=subtitle, body=body, script=script)


# --- background pipeline worker ------------------------------------------------


class PipelineWorker:
    """Runs fetch + score in a background thread; the UI polls its state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = {"running": False, "message": ""}

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _set(self, **kwargs) -> None:
        with self._lock:
            self._state.update(kwargs)

    def start(self, profile_path: str) -> bool:
        with self._lock:
            if self._state["running"]:
                return False
            self._state = {"running": True, "message": "Starting..."}
        self._thread = threading.Thread(target=self._run, args=(profile_path,), daemon=True)
        self._thread.start()
        return True

    def _run(self, profile_path: str) -> None:
        try:
            profile = Profile.load(profile_path)
            db = Database()  # own connection: sqlite objects are per-thread

            self._set(message="Fetching from sources...")
            results = fetch_all(profile.sources)
            new = 0
            failed_sources = []
            for source, outcome in results.items():
                if isinstance(outcome, Exception):
                    failed_sources.append(source)
                    continue
                new += sum(
                    db.upsert_job(job)
                    for job in outcome
                    if job.url and title_matches(job.title, profile.title_keywords)
                )

            provider = None
            try:
                provider = get_provider()
            except RuntimeError:
                pass  # misconfigured provider -> keyword fallback below
            scorer = LLMScorer(profile, provider) if provider else None
            jobs = db.unscored_jobs()
            scored = 0
            for i, row in enumerate(jobs, 1):
                self._set(message=f"Scoring {i}/{len(jobs)}: {row['title']} @ {row['company']}")
                try:
                    if scorer:
                        r = scorer.score(
                            row["title"], row["company"], row["location"], row["description"]
                        )
                        db.save_score(
                            row["id"], r.score, "llm", r.recommendation,
                            r.matched_skills, r.gaps, r.reasoning,
                        )
                    else:
                        pts, matched = keyword_score(
                            profile.skills, row["title"], row["description"]
                        )
                        db.save_score(row["id"], pts, "keyword", matched_skills=matched)
                    scored += 1
                except Exception:
                    continue  # one bad job never kills the run; re-run resumes

            summary = f"Done: {new} new jobs, {scored} scored"
            if not scorer:
                summary += " (keyword mode — no LLM configured)"
            if failed_sources:
                summary += f". Sources failed: {', '.join(failed_sources)}"
            self._set(running=False, message=summary)
        except Exception as exc:
            self._set(running=False, message=f"Pipeline failed: {exc}")


WORKER = PipelineWorker()


# --- rendering -------------------------------------------------------------------


def render_dashboard(
    counts: dict, rows: list, worker_state: dict, min_score: int = 0, status: str = ""
) -> str:
    running = worker_state.get("running")
    banner = ""
    if running:
        banner = (
            '<div class="banner">&#9203; <span id="worker-msg">'
            + _e(worker_state.get("message")) + "</span></div>"
        )
    elif worker_state.get("message"):
        banner = f'<div class="banner">{_e(worker_state["message"])}</div>'

    refresh = (
        '<form method="post" action="/refresh">'
        f'<button {"disabled" if running else ""}>Fetch &amp; score</button></form>'
    )
    status_opts = "".join(
        f'<option value="{s}" {"selected" if s == status else ""}>{s}</option>'
        for s in ("",) + VALID_STATUSES
    )
    filters = (
        '<form method="get" action="/" class="bar" style="margin:0">'
        f'<label class="meta">min score <input type="number" name="min" value="{min_score}" '
        'min="0" max="100" style="width:4.5rem"></label>'
        f'<label class="meta">status <select name="status">{status_opts}</select></label>'
        '<button class="ghost">Filter</button></form>'
    )

    if rows:
        body_rows = "".join(
            "<tr>"
            f'<td class="score">{r["score"]}</td>'
            f'<td><span class="badge rec">{_e(r["recommendation"]) or "—"}</span></td>'
            f'<td><a href="/job/{_e(r["id"])}">{_e(r["title"])}</a><br>'
            f'<span class="meta">{_e(r["company"])} &middot; {_e(r["location"]) or "—"} '
            f'&middot; via {_e(r["source"])}</span></td>'
            f'<td><span class="badge {_e(r["status"])}">{_e(r["status"])}</span></td>'
            "</tr>"
            for r in rows
        )
        table = (
            "<table><tr><th>Score</th><th>Rec</th><th>Job</th><th>Status</th></tr>"
            + body_rows + "</table>"
        )
    else:
        table = (
            '<div class="card">No scored jobs match. Hit <strong>Fetch &amp; score</strong> '
            "to pull jobs from your configured sources, or relax the filters.</div>"
        )

    subtitle = (
        f"{counts['total']} jobs &middot; {counts['scored']} scored &middot; "
        f"{counts['unscored']} unscored &middot; {counts['applied']} applied"
    )
    body = banner + f'<div class="bar">{refresh}{filters}</div>' + table
    return _page("AutoHawk", subtitle, body, script=_POLL_SCRIPT if running else "")


def render_job(row, letter_text: str | None = None, error: str = "") -> str:
    jid = _e(row["id"])
    error_html = f'<div class="banner error">{_e(error)}</div>' if error else ""

    score_html = ""
    if row["score"] is not None:
        gaps = _e(row["gaps"])
        score_html = (
            '<div class="card">'
            f'<span class="score" style="font-size:1.5rem">{row["score"]}</span> '
            f'<span class="badge rec">{_e(row["recommendation"]) or "unrated"}</span> '
            f'<span class="meta">via {_e(row["score_method"])}</span>'
            f'<p>{_e(row["reasoning"])}</p>'
            f'<p class="meta"><strong>Matches:</strong> {_e(row["matched_skills"]) or "—"}'
            + (f' &nbsp; <strong>Gaps:</strong> {gaps}' if gaps else "") + "</p></div>"
        )

    status_buttons = "".join(
        f'<form method="post" action="/job/{jid}/status">'
        f'<input type="hidden" name="status" value="{s}">'
        f'<button class="ghost" {"disabled" if row["status"] == s else ""}>{s}</button></form>'
        for s in ("shortlisted", "applied", "rejected", "archived")
    )
    letter_html = (
        f'<div class="card"><strong>Cover letter</strong><p class="letter">{_e(letter_text)}</p></div>'
        if letter_text
        else ""
    )

    body = (
        error_html
        + f'<p><a href="/">&larr; back to shortlist</a></p>'
        + f'<h2 style="margin:.2rem 0">{_e(row["title"])}</h2>'
        + f'<p class="meta">{_e(row["company"])} &middot; {_e(row["location"]) or "n/a"} &middot; '
        + f'via {_e(row["source"])} &middot; posted {_e(row["posted_at"]) or "?"} &middot; '
        + f'<span class="badge {_e(row["status"])}">{_e(row["status"])}</span></p>'
        + f'<p><a href="{_e(row["url"])}" rel="noopener">Open original posting &rarr;</a></p>'
        + score_html
        + '<div class="bar actions">'
        + status_buttons
        + f'<form method="post" action="/job/{jid}/letter"><button>Generate cover letter</button></form>'
        + "</div>"
        + letter_html
        + f'<div class="card desc">{_e(row["description"])}</div>'
    )
    return _page(f'{row["title"]} — AutoHawk', _e(row["company"]), body)


# --- HTTP plumbing ------------------------------------------------------------


def _find_letter(job_id: str, letters_dir: str = "letters") -> str | None:
    d = Path(letters_dir)
    if not d.is_dir():
        return None
    for path in sorted(d.glob(f"{job_id}_*.txt")):
        return path.read_text(encoding="utf-8")
    return None


def _save_letter(job_id: str, company: str, text: str, letters_dir: str = "letters") -> Path:
    out = Path(letters_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_company = "".join(c if c.isalnum() or c in "-_" else "_" for c in company)[:40]
    path = out / f"{job_id}_{safe_company}.txt"
    path.write_text(text, encoding="utf-8")
    return path


class Handler(BaseHTTPRequestHandler):
    server_version = "AutoHawk"

    # -- helpers --
    def _send_html(self, content: str, code: int = 200) -> None:
        data = content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: dict) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def _query(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def log_message(self, fmt, *args):  # quiet: no per-request stderr spam
        pass

    # -- routes --
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        db = Database()
        try:
            if path == "/":
                q = self._query()
                try:
                    min_score = max(0, int(q.get("min") or 0))
                except ValueError:
                    min_score = 0
                status = q.get("status", "")
                rows = db.shortlist(limit=100, min_score=min_score)
                if status in VALID_STATUSES:
                    rows = [r for r in rows if r["status"] == status]
                self._send_html(
                    render_dashboard(db.counts(), rows, WORKER.snapshot(), min_score, status)
                )
            elif path == "/api/progress":
                self._send_json(WORKER.snapshot())
            elif path.startswith("/job/") and path.count("/") == 2:
                job_id = path.split("/")[2]
                row = db.get_job(job_id)
                if row is None:
                    self._send_html(_page("Not found", "", "<p>No such job.</p>"), 404)
                    return
                error = self._query().get("err", "")[:300]
                self._send_html(render_job(row, _find_letter(job_id), error))
            else:
                self._send_html(_page("Not found", "", "<p>Nothing here.</p>"), 404)
        finally:
            db.close()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        db = Database()
        try:
            if path == "/refresh":
                WORKER.start(self.server.profile_path)  # type: ignore[attr-defined]
                self._redirect("/")
            elif len(parts) == 3 and parts[0] == "job" and parts[2] == "status":
                job_id = parts[1]
                status = self._form().get("status", "")
                if status in VALID_STATUSES and db.get_job(job_id) is not None:
                    db.set_status(job_id, status)
                self._redirect(f"/job/{quote(job_id)}")
            elif len(parts) == 3 and parts[0] == "job" and parts[2] == "letter":
                job_id = parts[1]
                row = db.get_job(job_id)
                if row is None:
                    self._redirect("/")
                    return
                try:
                    provider = get_provider()
                except RuntimeError as exc:
                    self._redirect(f"/job/{quote(job_id)}?err={quote(str(exc))}")
                    return
                if provider is None:
                    self._redirect(
                        f"/job/{quote(job_id)}?err="
                        + quote("Cover letters need an LLM: set ANTHROPIC_API_KEY or run Ollama.")
                    )
                    return
                try:
                    profile = Profile.load(self.server.profile_path)  # type: ignore[attr-defined]
                    text = generate_cover_letter(
                        profile, row["title"], row["company"], row["description"], provider
                    )
                    _save_letter(job_id, row["company"], text)
                    self._redirect(f"/job/{quote(job_id)}")
                except Exception as exc:
                    self._redirect(f"/job/{quote(job_id)}?err={quote(str(exc)[:200])}")
            else:
                self._send_html(_page("Not found", "", "<p>Nothing here.</p>"), 404)
        finally:
            db.close()


def serve(host: str, port: int, profile_path: str) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    server.profile_path = profile_path  # type: ignore[attr-defined]
    server.serve_forever()
