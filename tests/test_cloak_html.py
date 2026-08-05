"""Cloak HTML parsing and gate detection against synthetic fixtures."""

from __future__ import annotations

from pathlib import Path

from supersocks_media_scraper.adapters.cloak_html import (
    _parse_count,
    detect_gate,
    parse_cloak_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_reddit_post_fixture() -> None:
    html = _load("reddit_post.html")
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/announcements/comments/abc/title/?utm=1",
        final_url="https://www.reddit.com/r/announcements/comments/abc/title/",
        fetch_method="cloak",
    )
    assert result["status"] == "ok"
    assert result["platform"] == "reddit"
    assert result["content_kind"] == "post"
    assert "Example Reddit Post" in (result["title"] or "")
    assert "Visible public body" in result["text"]
    assert result["author"]["name"]
    assert result["published_at"]
    assert result["media"]
    assert result["media"][0]["kind"] == "image"
    assert "?" not in result["source_url"]
    assert result["metrics"]["likes"] == 42
    assert result["metrics"]["comments"] == 7
    assert result["comments"]
    assert result["action_required"] is None


def test_instagram_login_gate() -> None:
    html = _load("instagram_login.html")
    assert detect_gate(html, platform="instagram") == "login"
    result = parse_cloak_html(
        html,
        platform="instagram",
        source_url="https://www.instagram.com/p/EXAMPLE/",
    )
    assert result["status"] == "error"
    assert result["action_required"]["code"] == "needs-human"
    assert result["action_required"]["reason"] == "login"
    assert result["text"] == ""
    assert result["media"] == []


def test_reddit_challenge_and_rate_limit() -> None:
    challenge = _load("reddit_challenge.html")
    assert detect_gate(challenge, platform="reddit") in {"challenge", "captcha"}
    rate = _load("rate_limit.html")
    assert detect_gate(rate, platform="reddit") == "rate-limit"
    assert detect_gate("<html></html>", platform="reddit", http_status=429) == "rate-limit"


def test_facebook_consent_gate() -> None:
    html = _load("facebook_consent.html")
    assert detect_gate(html, platform="facebook") == "consent"


def test_parse_instagram_post_og_metrics_and_author() -> None:
    html = _load("instagram_post.html")
    result = parse_cloak_html(
        html,
        platform="instagram",
        source_url="https://www.instagram.com/p/EXAMPLE/",
    )
    assert result["status"] == "ok"
    assert result["metrics"]["likes"] == 268_000
    assert result["metrics"]["comments"] == 11_000
    assert result["author"]["handle"] == "example_creator"
    assert result["author"]["name"] == "Example Creator"
    assert "Public caption text from smoke render" in result["text"]


def test_parse_facebook_post_metrics_and_comments() -> None:
    html = _load("facebook_post.html")
    result = parse_cloak_html(
        html,
        platform="facebook",
        source_url="https://www.facebook.com/example/posts/123",
    )
    assert result["status"] == "ok"
    assert result["metrics"]["likes"] == 9400
    assert result["metrics"]["comments"] == 120
    assert result["metrics"]["shares"] == 32
    assert "Visible Facebook post body from metadata" in result["text"]
    assert len(result["comments"]) == 2
    assert result["comments"][0]["author"] == "Alice Dupont"
    assert "Alice comment text visible" in (result["comments"][0]["text"] or "")
    assert result["comments"][1]["author"] == "Bob Smith"
    assert "J'aime" not in (result["comments"][0]["text"] or "")


def test_parse_reddit_shreddit_post_by_url_id() -> None:
    html = _load("reddit_shreddit_post.html")
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/announcements/comments/abc123/title/",
        final_url="https://www.reddit.com/r/announcements/comments/abc123/title/",
    )
    assert result["status"] == "ok"
    assert result["title"] != "Wrong cached title"
    assert "Example Reddit Post" in (result["title"] or "")
    assert "Visible public body from shreddit slot=text-body only" in result["text"]
    assert "Wrong post body" not in result["text"]
    assert result["author"]["name"] == "example_user"
    assert result["published_at"] == "2026-01-15T12:00:00Z"
    assert result["metrics"]["likes"] == 42
    assert result["metrics"]["comments"] == 7
    assert len(result["comments"]) == 1
    assert result["comments"][0]["author"] == "commenter1"
    assert "Continuer ce fil" not in str(result["comments"])


def test_reddit_post_with_429_text_not_rate_limited() -> None:
    html = _load("reddit_post_with_429_text.html")
    assert detect_gate(html, platform="reddit") is None
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/api/comments/doc429/title/",
    )
    assert result["status"] == "ok"
    assert result["action_required"] is None
    assert "HTTP 429" in result["text"]


def test_parse_count_us_thousands_and_european_decimal() -> None:
    assert _parse_count("1,234") == 1234
    assert _parse_count("9,4 K") == 9400
    assert _parse_count("33 K") == 33_000


def test_parse_reddit_apostrophe_in_post_title() -> None:
    html = """
    <shreddit-post id="t3_abc123" author="user1" post-title="It's everyone's favorite day">
      <div slot="text-body">Body with apostrophe's intact and enough visible public text for parsing.</div>
    </shreddit-post>
    """
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/test/comments/abc123/title/",
    )
    assert result["status"] == "ok"
    assert result["title"] == "It's everyone's favorite day"
    assert "apostrophe's intact" in result["text"]


def test_parse_reddit_max_comments() -> None:
    html = _load("reddit_shreddit_post.html")
    extra = "".join(
        f'<shreddit-comment author="u{i}"><div slot="comment">Comment {i}</div></shreddit-comment>'
        for i in range(2, 8)
    )
    html = html.replace("</body>", f"{extra}</body>")
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/announcements/comments/abc123/title/",
        max_comments=3,
    )
    assert len(result["comments"]) == 3


def test_parse_facebook_nested_comment_articles() -> None:
    html = """
    <meta property="og:description" content="Nested Facebook post body from metadata fixture." />
    <div>Toutes les réactions : 33 K · 9,4 K commentaires · 17 K partages</div>
    <div role="article" aria-label="Commentaire de Parent User, 42 ans">
      <span>Parent comment visible</span>
      <div role="article" aria-label="Commentaire de Child User">
        <span>Child reply visible</span>
        <button>J'aime</button>
      </div>
    </div>
    """
    result = parse_cloak_html(
        html,
        platform="facebook",
        source_url="https://www.facebook.com/example/posts/456",
    )
    assert result["status"] == "ok"
    assert result["metrics"]["likes"] == 33_000
    assert result["metrics"]["comments"] == 9400
    assert result["metrics"]["shares"] == 17_000
    assert len(result["comments"]) == 2
    assert result["comments"][0]["author"] == "Parent User"
    assert "Parent comment visible" in (result["comments"][0]["text"] or "")
    assert "Child reply visible" not in (result["comments"][0]["text"] or "")
    assert result["comments"][1]["author"] == "Child User"
    assert "Child reply visible" in (result["comments"][1]["text"] or "")
    assert "J'aime" not in (result["comments"][1]["text"] or "")


def test_parse_facebook_comment_dedup_cleanup_and_max() -> None:
    """Real-capture shape: glued author/text, badge, age, score, duplicate desktop/mobile."""
    html = """
    <meta property="og:description" content="Visible Facebook post body from metadata smoke fixture." />
    <div role="article" aria-label="Commentaire de Evan Thomas il y a un an">
      <span>Evan Thomas</span><span>And this is why we all love Facebook! Great job on improving the platform</span>
      <span>Compte vérifié</span><span>1 an</span><span>42</span>
      <button>Voir les 3 réponses</button>
    </div>
    <div role="article" aria-label="Commentaire de Evan Thomas il y a un an">
      <span>Evan Thomas</span><span>And this is why we all love Facebook! Great job on improving the platform</span>
      <span>1 an</span>
    </div>
    <div role="article" aria-label="Comment by Verified User 2 days ago">
      <span>Verified User</span><span>We shipped 2 major updates this year.</span>
      <span>Verified account</span><span>99</span>
    </div>
    <div role="article" aria-label="Commentaire de Extra One">
      <span>Extra One</span><span>Third unique comment for max_comments cap.</span>
    </div>
    <div role="article" aria-label="Commentaire de Extra Two">
      <span>Extra Two</span><span>Fourth unique comment should not appear when capped.</span>
    </div>
    """
    result = parse_cloak_html(
        html,
        platform="facebook",
        source_url="https://www.facebook.com/example/posts/789",
        max_comments=3,
    )
    assert result["status"] == "ok"
    assert len(result["comments"]) == 3
    assert result["comments"][0]["author"] == "Evan Thomas"
    assert result["comments"][0]["text"] == (
        "And this is why we all love Facebook! Great job on improving the platform"
    )
    assert "Compte vérifié" not in (result["comments"][0]["text"] or "")
    assert "Voir les" not in (result["comments"][0]["text"] or "")
    assert result["comments"][1]["author"] == "Verified User"
    assert result["comments"][1]["text"] == "We shipped 2 major updates this year."
    assert "Verified account" not in (result["comments"][1]["text"] or "")
    assert not (result["comments"][1]["text"] or "").endswith("99")
    assert result["comments"][2]["author"] == "Extra One"

