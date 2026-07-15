from autohawk.utils import strip_html, title_matches, truncate


def test_strip_html_removes_tags_and_entities():
    raw = "<p>We need <strong>Python</strong> &amp; Docker.</p><ul><li>K8s</li></ul>"
    text = strip_html(raw)
    assert "<" not in text and ">" not in text
    assert "Python" in text and "& Docker" in text and "K8s" in text


def test_strip_html_handles_greenhouse_double_escaping():
    raw = "&lt;p&gt;Terraform &amp;amp; AWS&lt;/p&gt;"
    assert strip_html(raw) == "Terraform & AWS"


def test_title_matches_is_case_insensitive_substring():
    assert title_matches("Senior DevOps Engineer", ["devops"])
    assert not title_matches("Account Executive", ["devops", "security"])
    assert title_matches("Anything", [])  # empty list matches all


def test_truncate_respects_limit():
    text = "word " * 100
    out = truncate(text, 50)
    assert len(out) < 70 and out.endswith("…[truncated]")
    assert truncate("short", 50) == "short"
