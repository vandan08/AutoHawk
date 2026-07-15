"""Standalone HTML shortlist report — no external assets, opens anywhere."""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from pathlib import Path

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoHawk Shortlist</title>
<style>
  :root {{ --bg:#fdfcf9; --fg:#1c1917; --muted:#78716c; --card:#ffffff; --line:#e7e5e4; --accent:#b45309; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#131110; --fg:#e7e5e4; --muted:#a8a29e; --card:#1e1b19; --line:#312d2a; --accent:#f59e0b; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
         font:16px/1.55 Georgia, 'Times New Roman', serif; }}
  main {{ max-width:860px; margin:0 auto; }}
  h1 {{ font-size:1.9rem; margin:0 0 .25rem; }}
  .sub {{ color:var(--muted); margin-bottom:2rem; }}
  .job {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:1.1rem 1.3rem; margin-bottom:1rem; }}
  .row {{ display:flex; justify-content:space-between; gap:1rem; align-items:baseline; flex-wrap:wrap; }}
  .title a {{ color:var(--fg); text-decoration:none; font-weight:bold; font-size:1.12rem; }}
  .title a:hover {{ color:var(--accent); }}
  .score {{ font-size:1.35rem; font-weight:bold; color:var(--accent); white-space:nowrap; }}
  .meta {{ color:var(--muted); font-size:.92rem; margin:.15rem 0 .6rem; }}
  .rec {{ display:inline-block; font-size:.78rem; letter-spacing:.04em; text-transform:uppercase;
          border:1px solid var(--accent); color:var(--accent); border-radius:999px;
          padding:.1rem .6rem; margin-right:.5rem; }}
  .reasoning {{ font-size:.95rem; margin:.4rem 0 0; }}
  .skills {{ font-size:.88rem; color:var(--muted); margin-top:.4rem; }}
</style>
</head>
<body>
<main>
  <h1>AutoHawk Shortlist</h1>
  <p class="sub">{count} ranked matches &middot; generated {generated}</p>
  {cards}
</main>
</body>
</html>
"""

_CARD = """<div class="job">
  <div class="row">
    <span class="title"><a href="{url}">{title}</a></span>
    <span class="score">{score}</span>
  </div>
  <div class="meta">{company} &middot; {location} &middot; via {source}</div>
  <div><span class="rec">{recommendation}</span></div>
  <p class="reasoning">{reasoning}</p>
  <div class="skills"><strong>Matches:</strong> {matched} {gaps_html}</div>
</div>"""


def write_report(rows: list[sqlite3.Row], out_path: str | Path = "reports/shortlist.html") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for r in rows:
        e = lambda key: html.escape(str(r[key] or ""))
        gaps = e("gaps")
        cards.append(
            _CARD.format(
                url=e("url"),
                title=e("title"),
                score=r["score"],
                company=e("company"),
                location=e("location") or "—",
                source=e("source"),
                recommendation=e("recommendation") or "unrated",
                reasoning=e("reasoning"),
                matched=e("matched_skills") or "—",
                gaps_html=f"&nbsp;&nbsp;<strong>Gaps:</strong> {gaps}" if gaps else "",
            )
        )
    page = _PAGE.format(
        count=len(rows),
        generated=datetime.now().strftime("%d %b %Y, %H:%M"),
        cards="\n".join(cards) or "<p>No scored jobs yet. Run <code>autohawk score</code>.</p>",
    )
    out_path.write_text(page, encoding="utf-8")
    return out_path
