"""
Shared helpers for hamstouille.fr scrapers (blog, menus, diversification,
tire-allaitement). Stdlib + requests only.
"""
import re
from html.parser import HTMLParser

BASE_URL = "https://www.hamstouille.fr"
COOKIE = {"PHPSESSID": "dq60s92bsqpna0gdh0121f9v48"}


class TextExtractor(HTMLParser):
    """Convert HTML fragment to clean plain text. Drops scripts/styles."""

    BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6"}
    SKIP = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self):
        raw = " ".join(self.parts)
        lines = [" ".join(l.split()) for l in raw.split("\n")]
        return "\n".join(l for l in lines if l)


def to_text(html_fragment):
    """Plain text from an HTML fragment, used for search."""
    ext = TextExtractor()
    ext.feed(html_fragment or "")
    return ext.get_text()


# Tags we keep when sanitising HTML for the offline app
KEEP_TAGS = {
    "a", "b", "strong", "i", "em", "u",
    "p", "br", "div", "span",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "img", "video", "source", "iframe",
    "table", "tr", "td", "th", "thead", "tbody",
    "blockquote", "hr",
}
# Attributes we keep on each tag (others stripped)
KEEP_ATTRS = {
    "a": {"href", "target", "title"},
    "img": {"src", "alt", "title"},
    "video": {"controls", "poster"},
    "source": {"src", "type"},
    "iframe": {"src", "title", "allow", "allowfullscreen"},
}


def absolutize(url):
    """Make a URL absolute relative to BASE_URL."""
    if not url:
        return url
    url = url.strip()
    if url.startswith(("http://", "https://", "mailto:", "//", "#")):
        return url
    if url.startswith("/"):
        return BASE_URL + url
    return BASE_URL + "/" + url


class HtmlSanitizer(HTMLParser):
    """
    Re-emit a sanitised HTML fragment:
    - drops scripts/styles/comments and Word/MSO junk
    - drops every inline style="..." and class="..."
    - keeps only an allowlist of tags and attributes
    - absolutises hrefs/srcs
    """

    DROP = {"script", "style", "noscript", "meta", "link"}
    VOID = {"br", "img", "hr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._drop = 0
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in self.DROP:
            self._drop += 1
            return
        if self._drop:
            return
        if tag not in KEEP_TAGS:
            return
        kept = []
        keep_for_tag = KEEP_ATTRS.get(tag, set())
        for k, v in attrs:
            if k not in keep_for_tag:
                continue
            if k in ("href", "src") and v:
                v = absolutize(v)
            if v is None:
                kept.append(k)
            else:
                kept.append(f'{k}="{v.replace(chr(34), chr(39))}"')
        attrs_str = (" " + " ".join(kept)) if kept else ""
        if tag in self.VOID:
            self.out.append(f"<{tag}{attrs_str}>")
        else:
            self.out.append(f"<{tag}{attrs_str}>")

    def handle_endtag(self, tag):
        if tag in self.DROP and self._drop:
            self._drop -= 1
            return
        if self._drop:
            return
        if tag not in KEEP_TAGS or tag in self.VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag in self.VOID:
            self.handle_starttag(tag, attrs)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self._drop:
            return
        # escape minimal
        text = data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.out.append(text)

    def handle_entityref(self, name):
        if self._drop:
            return
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        if self._drop:
            return
        self.out.append(f"&#{name};")

    def handle_comment(self, data):
        return

    def get_html(self):
        html = "".join(self.out)
        # collapse runs of empty paragraphs and whitespace
        html = re.sub(r"\s+", " ", html)
        html = re.sub(r"(<br>\s*){3,}", "<br><br>", html)
        return html.strip()


def sanitize(html_fragment):
    """Clean an HTML fragment for safe inline rendering in the app."""
    if not html_fragment:
        return ""
    # Strip MSO/Word noise that confuses the parser
    html_fragment = re.sub(r"<!--.*?-->", "", html_fragment, flags=re.DOTALL)
    html_fragment = re.sub(r"<\?xml[^>]*\?>", "", html_fragment)
    html_fragment = re.sub(r"<o:[^>]+>.*?</o:[^>]+>", "", html_fragment, flags=re.DOTALL)
    html_fragment = re.sub(r"<o:[^>]+/?>", "", html_fragment)
    san = HtmlSanitizer()
    san.feed(html_fragment)
    return san.get_html()


def find_cross_refs(html_fragment):
    """Return list of {type, id, url} for any /recettes/N or /blog/N links."""
    refs = []
    seen = set()
    for m in re.finditer(
        r'href=["\'](?:https?://(?:www\.)?hamstouille\.fr)?(/(recettes|blog)/(\d+))',
        html_fragment or "",
    ):
        path, kind, _id = m.group(1), m.group(2), int(m.group(3))
        key = (kind, _id)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "type": "recipe" if kind == "recettes" else "blog",
            "id": _id,
            "url": path,
        })
    return refs
