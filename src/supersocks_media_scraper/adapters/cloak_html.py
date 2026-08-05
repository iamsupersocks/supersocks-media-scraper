"""Shared Cloak HTML parsing and gate detection for social media pages.

Adapted from supersocks-url-scraper cloak_social (MIT). Visible/public
extraction only — never claims exhaustiveness.
"""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any

from ..schema import GATE_LABELS, build_action_required, make_result
from ..sanitize import trim_text
from ._util import clean_text

CLOAK_PLATFORMS = frozenset({"reddit", "instagram", "facebook"})
MIN_USEFUL_CHARS = 40
MAX_COMMENTS = 20

_LOGIN_MARKERS = (
    "log in",
    "sign in",
    "sign up",
    "create an account",
    "connexion",
    "identifiez-vous",
    "you must log in",
    "login to continue",
    "log in to continue",
    "please log in",
    "authwall",
    "checkpoint",
)
_MFA_MARKERS = (
    "two-factor",
    "two factor",
    "2fa",
    "multi-factor",
    "mfa",
    "verification code",
    "authenticator app",
    "enter the code",
    "one-time code",
    "one time password",
)
_CAPTCHA_MARKERS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "js_challenge",
)
_CHALLENGE_MARKERS = (
    "are you a robot",
    "security check",
    "unusual traffic",
    "verify you are human",
    "prove your humanity",
    "press & hold",
    "js_challenge",
)
_CONSENT_MARKERS = (
    "cookie consent",
    "consentement",
    "before you continue",
    "accept all cookies",
    "accepter tous les cookies",
    "autoriser tous les cookies",
    "privacy preference center",
)
_STRONG_CONSENT_MARKERS = ("autoriser tous les cookies",)
_RATE_LIMIT_MARKERS = (
    "too many requests",
    "rate limit",
    "rate-limit",
    "you are being rate limited",
    "try again later",
)

_REDDIT_SHREDDIT_TITLE = re.compile(
    r"<shreddit-title[^>]*title=[\"']([^\"']+)[\"']",
    re.I,
)
_REDDIT_COMMENT_SKIP = (
    "continuer ce fil",
    "continue this thread",
    "recommended for you",
    "recommendations",
    "promoted",
    "publicité",
    "advertisement",
    "banner",
)
_OG_IG_LIKES = re.compile(
    r"(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*(?:likes?|j'?aime)",
    re.I,
)
_OG_IG_COMMENTS = re.compile(
    r"(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*(?:comments?|commentaires?)",
    re.I,
)
_FB_COMMENT_LABEL = re.compile(r"^(?:Commentaire de|Comment by)\s+(.+)$", re.I)
_FB_VISIBLE_METRICS = {
    "likes": re.compile(
        r"(?:toutes les )?r[ée]actions?\s*:?\s*(\d[\d,\.\s\u00a0]*\s*[kKmM]?)",
        re.I,
    ),
    "comments": re.compile(
        r"(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*(?:comments?|commentaires?)",
        re.I,
    ),
    "shares": re.compile(
        r"(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*(?:shares?|partages?)",
        re.I,
    ),
}
_REDDIT_POST_CONTENT = re.compile(
    r"<(?:div|p|h1)[^>]*(?:slot=[\"']text-body[\"']|id=[\"']post-title[\"']|data-testid=[\"']post-content[\"']|"
    r"class=[\"'][^\"']*(?:Post|post-content|RichTextJSON-root)[^\"']*[\"'])[^>]*>(.*?)</(?:div|p|h1)>",
    re.I | re.S,
)
_AUTHOR_SELECTORS = (
    re.compile(
        r"<meta[^>]+(?:name|property)=[\"'](?:author|article:author|og:article:author)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.I,
    ),
    re.compile(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:name|property)=[\"'](?:author|article:author|og:article:author)[\"']",
        re.I,
    ),
    re.compile(
        r"<a\b[^>]*(?:class=[\"'][^\"']*(?:author|Author|username)[^\"']*[\"']|rel=[\"']author[\"'])[^>]*>(.*?)</a>",
        re.I | re.S,
    ),
)
_TIME_SELECTORS = (
    re.compile(
        r"<meta[^>]+(?:name|property)=[\"'](?:article:published_time|og:updated_time|datePublished)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.I,
    ),
    re.compile(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:name|property)=[\"'](?:article:published_time|og:updated_time|datePublished)[\"']",
        re.I,
    ),
    re.compile(r"<time\b[^>]*(?:datetime|content)=[\"']([^\"']+)[\"']", re.I),
)
_OG_IMAGE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_OG_IMAGE_ALT = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image:alt[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_OG_VIDEO = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?:og:video|og:video:url|twitter:player:stream)[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_METRIC_PATTERNS = {
    "likes": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*"
        r"(?:likes?|j'?aime|reactions?|réactions?)[\"']",
        re.I,
    ),
    "comments": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*"
        r"(?:comments?|commentaires?)[\"']",
        re.I,
    ),
    "shares": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*"
        r"(?:shares?|partages?)[\"']",
        re.I,
    ),
    "views": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.\s\u00a0]*\s*[kKmM]?)\s*"
        r"(?:views?|vues?)[\"']",
        re.I,
    ),
}

def _strip_embedded_markup(markup: str) -> str:
    text = markup or ""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    for tag in ("script", "style", "noscript", "template"):
        text = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", " ", text, flags=re.I | re.S)
    return text


_SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


class _HtmlElement:
    __slots__ = ("tag", "attrs", "children", "text_parts")

    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag = tag.lower()
        self.attrs = {k.lower(): (v or "") for k, v in attrs}
        self.children: list[_HtmlElement] = []
        self.text_parts: list[str] = []

    def attr(self, name: str) -> str:
        return self.attrs.get(name.lower(), "")

    def slot(self) -> str:
        return self.attr("slot")

    def iter_descendants(self) -> Any:
        for child in self.children:
            yield child
            yield from child.iter_descendants()

    def text_content(self, *, skip_tags: frozenset[str] = _SKIP_TAGS) -> str:
        parts: list[str] = []

        def walk(node: _HtmlElement) -> None:
            if node.tag in skip_tags:
                return
            parts.extend(node.text_parts)
            for child in node.children:
                walk(child)

        walk(self)
        return clean_text("".join(parts))


class _CloakTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlElement("root", [])
        self._stack: list[_HtmlElement] = [self.root]
        self._skip_depth = 0

    def _append(self, tag: str, attrs: list[tuple[str, str | None]]) -> _HtmlElement | None:
        if self._skip_depth:
            return None
        elem = _HtmlElement(tag, attrs)
        self._stack[-1].children.append(elem)
        return elem

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in _SKIP_TAGS:
            self._skip_depth += 1
            return
        elem = self._append(lowered, attrs)
        if elem is not None and lowered not in _VOID_TAGS:
            self._stack.append(elem)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if len(self._stack) > 1 and self._stack[-1].tag == lowered:
            self._stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        lowered = tag.lower()
        if self._skip_depth or lowered in _SKIP_TAGS:
            return
        if len(self._stack) > 1 and self._stack[-1].tag == lowered:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._stack[-1].text_parts.append(data)


def _parse_html_tree(markup: str) -> _HtmlElement:
    parser = _CloakTreeParser()
    parser.feed(markup or "")
    parser.close()
    return parser.root


def _visible_text(markup: str) -> str:
    return clean_text(_parse_html_tree(markup).text_content())


def _meta_content(markup: str, *, name: str | None = None, prop: str | None = None) -> str:
    attr = "name" if name else "property"
    key = name or prop
    if not key:
        return ""
    escaped = re.escape(key)
    patterns = [
        rf"<meta[^>]+{attr}=[\"']{escaped}[\"'][^>]+content=[\"']([^\"']{{1,5000}})[\"']",
        rf"<meta[^>]+content=[\"']([^\"']{{1,5000}})[\"'][^>]+{attr}=[\"']{escaped}[\"']",
    ]
    for pattern in patterns:
        match = re.search(pattern, markup or "", re.I | re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def _json_ld_nodes(markup: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',
        markup or "",
        re.I | re.S,
    ):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item and isinstance(item["@graph"], list):
                    stack.extend(item["@graph"])
                else:
                    nodes.append(item)
            elif isinstance(item, list):
                stack.extend(item)
    return nodes


def _visible_challenge_text(*parts: object) -> str:
    return " ".join(clean_text(part).lower() for part in parts if part)


def detect_gate(
    markup: str,
    *,
    platform: str,
    page_title: str | None = None,
    http_status: int | None = None,
) -> str | None:
    """Return needs-human reason: login|mfa|captcha|consent|challenge|rate-limit."""
    if http_status == 429:
        return "rate-limit"
    visible = _strip_embedded_markup(markup)
    blob = clean_text(visible).lower()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", visible, re.I | re.S)
    html_title = title_match.group(1) if title_match else None
    challenge_blob = _visible_challenge_text(blob, page_title, html_title)
    if not challenge_blob:
        return None
    if any(marker in challenge_blob for marker in _RATE_LIMIT_MARKERS):
        return "rate-limit"
    if any(marker in challenge_blob for marker in _MFA_MARKERS):
        return "mfa"
    if any(marker in challenge_blob for marker in _CAPTCHA_MARKERS):
        return "captcha"
    if any(marker in challenge_blob for marker in _CHALLENGE_MARKERS):
        return "challenge"
    login_hits = sum(1 for marker in _LOGIN_MARKERS if marker in blob)
    useful_meta = bool(
        _meta_content(markup, prop="og:description")
        or _meta_content(markup, name="description")
        or _meta_content(markup, prop="og:title")
    )
    if login_hits >= 2 and not useful_meta:
        return "login"
    if platform == "instagram" and "login • instagram" in blob and not useful_meta:
        return "login"
    if platform == "facebook" and ("log into facebook" in blob or "créer un compte" in blob) and not useful_meta:
        return "login"
    if (
        platform == "reddit"
        and ("log in" in blob and "sign up" in blob)
        and "shreddit-post" not in visible.lower()
        and not useful_meta
    ):
        return "login"
    if any(marker in blob for marker in _STRONG_CONSENT_MARKERS):
        return "consent"
    if any(marker in blob for marker in _CONSENT_MARKERS) and len(blob) < 600 and not useful_meta:
        return "consent"
    return None


def _parse_count(raw: str) -> int | None:
    text = (raw or "").strip().lower().replace("\u00a0", " ")
    if not text:
        return None
    mult = 1
    if re.search(r"\s*k\s*$", text) or text.endswith("k"):
        mult = 1_000
        text = re.sub(r"\s*k\s*$", "", text).rstrip("k").strip()
    elif re.search(r"\s*m\s*$", text) or text.endswith("m"):
        mult = 1_000_000
        text = re.sub(r"\s*m\s*$", "", text).rstrip("m").strip()
    compact = text.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", compact):
        compact = compact.replace(",", "")
    elif "," in compact and "." not in compact:
        if re.fullmatch(r"\d+,\d+", compact):
            compact = compact.replace(",", ".")
        else:
            compact = compact.replace(",", "")
    else:
        compact = compact.replace(",", "")
    try:
        return int(float(compact) * mult)
    except ValueError:
        return None


def _reddit_post_id_from_url(url: str) -> str | None:
    match = re.search(r"/comments/([a-z0-9]+)/", url or "", re.I)
    return match.group(1).lower() if match else None


def _find_elements(root: _HtmlElement, tag: str) -> list[_HtmlElement]:
    tag = tag.lower()
    return [elem for elem in root.iter_descendants() if elem.tag == tag]


def _select_shreddit_post(root: _HtmlElement, source_url: str) -> _HtmlElement | None:
    post_id = _reddit_post_id_from_url(source_url)
    posts = _find_elements(root, "shreddit-post")
    fallback = posts[0] if posts else None
    if not post_id:
        return fallback
    for post in posts:
        pid = (post.attr("id") or post.attr("post-id")).lower()
        if post_id in pid:
            return post
    return fallback


def _reddit_post_text_bodies(post: _HtmlElement) -> list[str]:
    bodies: list[str] = []
    for elem in post.iter_descendants():
        if elem.tag == "shreddit-post-text-body":
            text = elem.text_content()
            if text and text not in bodies:
                bodies.append(text)
        elif elem.slot() == "text-body":
            text = elem.text_content()
            if text and text not in bodies:
                bodies.append(text)
    return bodies


def _reddit_comment_body(comment: _HtmlElement) -> str:
    for elem in comment.iter_descendants():
        if elem.slot() == "comment":
            return elem.text_content()
    return ""


def _should_skip_reddit_comment(text: str) -> bool:
    lower = (text or "").lower()
    if not lower:
        return True
    if any(skip in lower for skip in _REDDIT_COMMENT_SKIP):
        return True
    if "sml.load" in lower or "actionrow" in lower:
        return True
    return False


def _extract_reddit_post_fields(root: _HtmlElement, source_url: str) -> dict[str, Any]:
    post = _select_shreddit_post(root, source_url)
    if post is None:
        return {}
    out: dict[str, Any] = {}
    author = post.attr("author")
    if author:
        out["author"] = {"name": author, "handle": author, "url": None}
    ts = post.attr("created-timestamp")
    if ts:
        out["published_at"] = ts
    metrics: dict[str, int | None] = {"likes": None, "comments": None, "shares": None, "views": None}
    score = post.attr("score")
    comment_count = post.attr("comment-count")
    if score:
        try:
            metrics["likes"] = int(score)
        except ValueError:
            metrics["likes"] = _parse_count(score)
    if comment_count:
        try:
            metrics["comments"] = int(comment_count)
        except ValueError:
            metrics["comments"] = _parse_count(comment_count)
    out["metrics"] = metrics
    post_title = post.attr("post-title")
    bodies = _reddit_post_text_bodies(post)
    if bodies:
        out["body"] = "\n\n".join(bodies).strip()
    elif post_title:
        out["body"] = clean_text(post_title)
    else:
        out["body"] = ""
    return out


def _extract_instagram_author(markup: str) -> dict[str, str | None]:
    og_title = _meta_content(markup, prop="og:title")
    og_desc = _meta_content(markup, prop="og:description")
    name = None
    handle = None
    title_match = re.search(r"^(.+?)\s+\(@([\w.]+)\)", og_title or "")
    if title_match:
        name = clean_text(title_match.group(1))
        handle = title_match.group(2)
    if not handle:
        for source in (og_desc, og_title):
            at_match = re.search(r"@([\w.]+)", source or "")
            if at_match:
                handle = at_match.group(1)
                break
    if not handle:
        on_ig = re.search(r"([\w.]+)\s+on\s+Instagram", og_desc or "", re.I)
        if on_ig:
            handle = on_ig.group(1).lstrip("@")
    if not name and handle:
        name = f"@{handle}"
    return {"name": name, "handle": handle, "url": None}


def _instagram_caption_from_og(description: str) -> str:
    if not description:
        return ""
    quoted = re.search(
        r"on Instagram:\s*(?:[«\"'](.+?)[»\"']|\u201c(.+?)\u201d)",
        description,
        re.I | re.S,
    )
    if quoted:
        return clean_text(quoted.group(1) or quoted.group(2) or "")
    stripped = re.sub(
        r"^[\d,\.\s\u00a0]*[kKmM]?\s*(?:likes?|comments?|j'?aime|commentaires?)[,\s-]*",
        "",
        description,
        count=2,
        flags=re.I,
    )
    stripped = re.sub(r"^@[\w.]+\s+on Instagram:\s*", "", stripped, flags=re.I)
    stripped = re.sub(r"^[\w.]+\s+on Instagram:\s*", "", stripped, flags=re.I)
    return clean_text(stripped.strip(" \"'«»"))


def _fb_author_from_label(label: str) -> str:
    text = clean_text(label)
    text = re.sub(r",?\s*\d+\s*(?:ans|years?\s*old)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*[·•]\s*\d+.*$", "", text)
    return text.strip()


def _fb_comment_text_from_elem(elem: _HtmlElement) -> str:
    skip = frozenset({"button", "script", "style"})
    parts: list[str] = []

    def walk(node: _HtmlElement) -> None:
        if node is not elem and node.tag in {"div", "article"}:
            if node.attr("role") == "article" and _FB_COMMENT_LABEL.match(node.attr("aria-label")):
                return
        if node.tag in skip:
            return
        if node.attr("role") in {"button", "menu", "toolbar"}:
            return
        parts.extend(node.text_parts)
        for child in node.children:
            walk(child)

    walk(elem)
    text = clean_text("".join(parts))
    for noise in (
        r"\bJ['']aime\b",
        r"\bLike\b",
        r"\bRépondre\b",
        r"\bReplies\b",
        r"\bRéponses\b",
        r"\b\d+\s*(?:réactions?|reactions?|commentaires?|comments?|partages?|shares?)\b",
    ):
        text = re.sub(noise, " ", text, flags=re.I)
    return clean_text(text)


def _extract_facebook_comments(root: _HtmlElement, *, max_comments: int = MAX_COMMENTS) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for elem in root.iter_descendants():
        if elem.tag not in {"div", "article"}:
            continue
        if elem.attr("role") != "article":
            continue
        aria = elem.attr("aria-label")
        match = _FB_COMMENT_LABEL.match(aria)
        if not match:
            continue
        author = _fb_author_from_label(match.group(1)) or None
        text = _fb_comment_text_from_elem(elem)
        if not author or not text or len(text) < 2:
            continue
        comments.append({"author": author, "text": trim_text(text, 500), "published_at": None})
        if len(comments) >= max_comments:
            break
    return comments


def _extract_reddit_comments(
    root: _HtmlElement,
    source_url: str,
    *,
    max_comments: int = MAX_COMMENTS,
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for comment in _find_elements(root, "shreddit-comment"):
        author = comment.attr("author") or None
        text = _reddit_comment_body(comment)
        if _should_skip_reddit_comment(text):
            continue
        if not text or len(text) < 2:
            continue
        comments.append(
            {
                "author": author,
                "text": trim_text(text, 500),
                "published_at": comment.attr("created-timestamp") or None,
            }
        )
        if len(comments) >= max_comments:
            break
    if comments:
        return comments
    return _extract_generic_comments(root, max_comments=max_comments)


def _extract_generic_comments(root: _HtmlElement, *, max_comments: int = MAX_COMMENTS) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for elem in root.iter_descendants():
        if elem.tag not in {"div", "li", "article"}:
            continue
        testid = elem.attr("data-testid")
        classes = elem.attr("class")
        if testid != "comment" and "comment" not in classes.lower():
            continue
        text = elem.text_content()
        if not text or len(text) < 2:
            continue
        author = None
        for child in elem.iter_descendants():
            if child.tag in {"a", "span"} and "author" in child.attr("class").lower():
                author = child.text_content() or None
                if author:
                    break
        comments.append({"author": author, "text": trim_text(text, 500), "published_at": None})
        if len(comments) >= max_comments:
            break
    return comments


def _extract_metrics(
    markup: str,
    *,
    platform: str = "",
    og_description: str = "",
    reddit_fields: dict[str, Any] | None = None,
    visible: str = "",
) -> dict[str, int | None]:
    out: dict[str, int | None] = {"likes": None, "comments": None, "shares": None, "views": None}
    if reddit_fields and isinstance(reddit_fields.get("metrics"), dict):
        for key in out:
            value = reddit_fields["metrics"].get(key)
            if value is not None:
                out[key] = value
    for key, pattern in _METRIC_PATTERNS.items():
        if out[key] is not None:
            continue
        match = pattern.search(markup or "")
        if match:
            out[key] = _parse_count(match.group(1))
    if platform == "facebook" and visible:
        for key, pattern in _FB_VISIBLE_METRICS.items():
            if out[key] is not None:
                continue
            match = pattern.search(visible)
            if match:
                out[key] = _parse_count(match.group(1))
    if platform == "instagram" and og_description:
        if out["likes"] is None:
            match = _OG_IG_LIKES.search(og_description)
            if match:
                out["likes"] = _parse_count(match.group(1))
        if out["comments"] is None:
            match = _OG_IG_COMMENTS.search(og_description)
            if match:
                out["comments"] = _parse_count(match.group(1))
    return out


def _extract_media(markup: str) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    alt = None
    alt_match = _OG_IMAGE_ALT.search(markup or "")
    if alt_match:
        alt = clean_text(alt_match.group(1)) or None
    for match in _OG_IMAGE.finditer(markup or ""):
        url = clean_text(match.group(1))
        if url:
            media.append({"kind": "image", "url": url, "alt": alt})
            break
    for match in _OG_VIDEO.finditer(markup or ""):
        url = clean_text(match.group(1))
        if url:
            media.append({"kind": "video", "url": url, "alt": None})
            break
    # Thumbnail: reuse first image when a video is present.
    if any(item["kind"] == "video" for item in media) and any(item["kind"] == "image" for item in media):
        image = next(item for item in media if item["kind"] == "image")
        media.append({"kind": "thumbnail", "url": image["url"], "alt": image.get("alt")})
    return media


def _extract_comments(
    root: _HtmlElement,
    *,
    platform: str = "",
    source_url: str = "",
    max_comments: int = MAX_COMMENTS,
) -> list[dict[str, Any]]:
    if platform == "facebook":
        fb = _extract_facebook_comments(root, max_comments=max_comments)
        if fb:
            return fb
    if platform == "reddit":
        return _extract_reddit_comments(root, source_url, max_comments=max_comments)
    return _extract_generic_comments(root, max_comments=max_comments)


def _extract_author(
    markup: str,
    nodes: list[dict[str, Any]],
    *,
    platform: str = "",
    reddit_fields: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    if reddit_fields and isinstance(reddit_fields.get("author"), dict):
        author = reddit_fields["author"]
        if author.get("name") or author.get("handle"):
            return {
                "name": author.get("name"),
                "handle": author.get("handle"),
                "url": author.get("url"),
            }
    if platform == "instagram":
        ig_author = _extract_instagram_author(markup)
        if ig_author.get("name") or ig_author.get("handle"):
            return ig_author
    name = None
    for pattern in _AUTHOR_SELECTORS:
        match = pattern.search(markup or "")
        if match:
            value = clean_text(match.group(1))
            if value:
                name = value
                break
    if not name:
        for node in nodes:
            for key in ("author", "creator", "publisher"):
                value = node.get(key)
                if isinstance(value, dict):
                    candidate = clean_text(value.get("name") or value.get("@id") or "")
                    if candidate:
                        name = candidate
                        break
                elif isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, dict):
                        candidate = clean_text(first.get("name") or "")
                    else:
                        candidate = clean_text(first)
                    if candidate:
                        name = candidate
                        break
                else:
                    candidate = clean_text(value)
                    if candidate:
                        name = candidate
                        break
            if name:
                break
    handle = None
    if name and name.startswith("@"):
        handle = name.lstrip("@")
    return {"name": name, "handle": handle, "url": None}


def _extract_published_at(
    markup: str,
    nodes: list[dict[str, Any]],
    *,
    reddit_fields: dict[str, Any] | None = None,
) -> str | None:
    if reddit_fields and reddit_fields.get("published_at"):
        return str(reddit_fields["published_at"])
    for pattern in _TIME_SELECTORS:
        match = pattern.search(markup or "")
        if match:
            value = clean_text(match.group(1))
            if value:
                return value
    for node in nodes:
        for key in ("datePublished", "uploadDate", "dateCreated", "dateModified"):
            value = clean_text(node.get(key))
            if value:
                return value
    return None


def _platform_body(
    root: _HtmlElement,
    markup: str,
    *,
    platform: str,
    source_url: str = "",
    og_description: str = "",
    reddit_fields: dict[str, Any] | None = None,
) -> str:
    chunks: list[str] = []
    if platform == "reddit":
        if reddit_fields and reddit_fields.get("body"):
            chunks.append(str(reddit_fields["body"]))
        else:
            title = _REDDIT_SHREDDIT_TITLE.search(markup or "")
            if title:
                chunks.append(clean_text(title.group(1)))
            for match in _REDDIT_POST_CONTENT.finditer(markup or ""):
                text = clean_text(match.group(1))
                if text and text not in chunks:
                    chunks.append(text)
            if source_url:
                post = _select_shreddit_post(root, source_url)
                if post:
                    for text in _reddit_post_text_bodies(post):
                        if text not in chunks:
                            chunks.append(text)
    elif platform == "instagram":
        caption = _instagram_caption_from_og(og_description)
        if caption:
            chunks.append(caption)
        for elem in _find_elements(root, "article"):
            text = elem.text_content()
            if text and text not in chunks:
                chunks.append(text)
                break
    elif platform == "facebook":
        og = og_description or _meta_content(markup, prop="og:description")
        if og and len(og) >= 20:
            chunks.append(og)
        for elem in root.iter_descendants():
            preview = elem.attr("data-ad-preview")
            testid = elem.attr("data-testid")
            classes = elem.attr("class")
            if preview == "message" or testid == "post_message" or "usercontent" in classes.lower():
                text = elem.text_content()
                if text and text not in chunks:
                    chunks.append(text)
    return "\n\n".join(chunks).strip()


def infer_content_kind(url: str, platform: str) -> str:
    path = (url or "").lower()
    if platform == "instagram":
        if "/reel/" in path or "/reels/" in path:
            return "reel"
        if "/stories/" in path:
            return "story"
        if "/p/" in path:
            return "post"
        parts = [p for p in path.split("/") if p and p not in {"https:", "http:"}]
        if len(parts) <= 2:
            return "profile"
    if platform == "reddit":
        if "/comments/" in path:
            return "post"
        if "/user/" in path or "/u/" in path:
            return "profile"
    if platform == "facebook":
        if "/videos/" in path or "/watch" in path:
            return "video"
        if "/posts/" in path or "/permalink" in path or "story_fbid" in path:
            return "post"
    return "post"


def parse_cloak_html(
    markup: str,
    *,
    platform: str,
    source_url: str,
    final_url: str | None = None,
    page_title: str | None = None,
    max_chars: int = 4000,
    fetch_method: str = "cloak",
    extra_warnings: list[str] | None = None,
    http_status: int | None = None,
    max_comments: int = MAX_COMMENTS,
) -> dict[str, Any]:
    """Parse rendered social HTML into the media-scraper JSON contract."""
    warnings = list(extra_warnings or [])
    gate = detect_gate(markup, platform=platform, page_title=page_title, http_status=http_status)
    nodes = _json_ld_nodes(markup)
    title = (
        _meta_content(markup, prop="og:title")
        or _meta_content(markup, name="twitter:title")
        or clean_text(page_title)
        or None
    )
    if not title and platform == "reddit":
        match = _REDDIT_SHREDDIT_TITLE.search(markup or "")
        if match:
            title = clean_text(match.group(1)) or None
    for node in nodes:
        if not title:
            candidate = clean_text(node.get("headline") or node.get("name") or node.get("title"))
            if candidate:
                title = candidate
                break

    description = (
        _meta_content(markup, prop="og:description")
        or _meta_content(markup, name="description")
        or _meta_content(markup, name="twitter:description")
    )
    root = _parse_html_tree(markup)
    visible = _visible_text(markup)
    reddit_fields = (
        _extract_reddit_post_fields(root, final_url or source_url)
        if platform == "reddit"
        else {}
    )
    if platform == "reddit" and reddit_fields:
        post = _select_shreddit_post(root, final_url or source_url)
        if post:
            post_title = post.attr("post-title")
            if post_title:
                title = clean_text(post_title) or title
            if not title:
                for elem in _find_elements(post, "shreddit-title"):
                    t = elem.attr("title")
                    if t:
                        title = clean_text(t) or title
                        break
                if not title:
                    match = _REDDIT_SHREDDIT_TITLE.search(markup or "")
                    if match:
                        title = clean_text(match.group(1)) or title
    body = _platform_body(
        root,
        markup,
        platform=platform,
        source_url=final_url or source_url,
        og_description=description,
        reddit_fields=reddit_fields,
    )
    for node in nodes:
        for key in ("articleBody", "text", "description", "caption"):
            value = clean_text(node.get(key))
            if value and value not in body:
                body = f"{body}\n\n{value}".strip() if body else value
    text = trim_text(body or description or "", max(50, min(int(max_chars or 4000), 20_000)))
    author = _extract_author(
        markup,
        nodes,
        platform=platform,
        reddit_fields=reddit_fields,
    )
    published_at = _extract_published_at(markup, nodes, reddit_fields=reddit_fields)
    metrics = _extract_metrics(
        markup,
        platform=platform,
        og_description=description,
        reddit_fields=reddit_fields,
        visible=visible,
    )
    media = _extract_media(markup)
    comments = _extract_comments(
        root,
        platform=platform,
        source_url=final_url or source_url,
        max_comments=max(0, int(max_comments)),
    )
    useful = len(text) >= MIN_USEFUL_CHARS or bool(title and media)
    content_kind = infer_content_kind(final_url or source_url, platform)

    action = None
    if gate:
        label = GATE_LABELS.get(gate, gate)
        warnings.append(
            f"{platform} blocked by {label}; warm an operator-owned Cloak profile once "
            f"(MEDIA_BROWSER_PROFILES_ROOT/{platform}). Never automate login/MFA/CAPTCHA."
        )
        status = "error" if gate in {"captcha", "consent", "challenge", "mfa", "rate-limit"} else (
            "partial" if useful else "error"
        )
        text = ""
        media = []
        comments = []
        action = build_action_required(platform=platform, reason=gate)
    elif useful:
        status = "ok"
    elif title or text:
        status = "partial"
        warnings.append(f"{platform} rendered but useful text looks thin")
    else:
        status = "error"
        warnings.append(f"{platform} Cloak render produced no readable title/text")

    return make_result(
        status=status,
        platform=platform,
        content_kind=content_kind,
        source_url=source_url,
        final_url=final_url or source_url,
        title=title,
        text=text,
        author=author,
        published_at=published_at,
        metrics=metrics,
        media=media,
        comments=comments,
        warnings=warnings,
        action_required=action,
        fetch_method=fetch_method,
    )
