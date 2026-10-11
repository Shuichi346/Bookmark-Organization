import hashlib
import html
from collections import Counter
from html.parser import HTMLParser
from uuid import uuid4

from bookmark_organization.schemas import AppError


def uid() -> str:
    return str(uuid4())


class BookmarkParser(HTMLParser):
    """Netscape DT/P tags are often unclosed; DL alone controls ancestry."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict] = []
        self.stack = ["root"]
        self.pending: str | None = None
        self.current: dict | None = None
        self.parts: list[str] = []
        self.links = 0
        self.root_dl = False

    def finish(self):
        if self.current:
            self.current["name"] = "".join(self.parts).strip()
            self.nodes.append(self.current)
            if self.current["kind"] == "folder":
                self.pending = self.current["id"]
            self.current = None
            self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"h3", "a"}:
            self.finish()
            values = dict(attrs)
            if tag == "a":
                self.links += 1
                if values.get("href") is None:
                    raise AppError("invalid_import")
            self.current = {
                "id": uid(),
                "kind": "folder" if tag == "h3" else "bookmark",
                "name": "",
                "parent": self.stack[-1],
                "order": len(self.nodes),
                "attrs": {k: v or "" for k, v in attrs if k != "href"},
            }
            if tag == "a":
                self.current["url"] = values["href"]
        elif tag == "dl":
            self.finish()
            if self.pending:
                self.stack.append(self.pending)
                self.pending = None
            elif not self.root_dl:
                self.root_dl = True
            else:
                raise AppError("invalid_import")

    def handle_endtag(self, tag):
        if tag in {"h3", "a"}:
            self.finish()
        elif tag == "dl":
            self.finish()
            if len(self.stack) > 1:
                self.stack.pop()

    def handle_data(self, data):
        if self.current:
            self.parts.append(data)


def parse(raw: bytes) -> list[dict]:
    if len(raw) > 25 * 1024 * 1024:
        raise AppError("import_too_large")
    try:
        text = raw.decode("utf-8-sig")
        parser = BookmarkParser()
        parser.feed(text)
        parser.finish()
    except (UnicodeError, ValueError) as exc:
        raise AppError("invalid_import") from exc
    if not parser.root_dl or parser.links != sum(
        n["kind"] == "bookmark" for n in parser.nodes
    ):
        raise AppError("invalid_import")
    return parser.nodes


def structural(nodes: list[dict]) -> list:
    def children(parent):
        result = []
        for n in sorted(
            (n for n in nodes if n["parent"] == parent), key=lambda n: n["order"]
        ):
            attrs = dict(n["attrs"])
            result.append(
                (
                    n["kind"],
                    n["name"],
                    n.get("url"),
                    attrs,
                    children(n["id"]) if n["kind"] == "folder" else [],
                )
            )
        return result

    return children("root")


def export(nodes: list[dict]) -> bytes:
    seen = set()
    out = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]

    def children(parent, depth):
        for n in sorted(
            (n for n in nodes if n["parent"] == parent), key=lambda n: n["order"]
        ):
            if n["id"] in seen:
                raise AppError("integrity_failed", 409)
            seen.add(n["id"])
            # Only syntactically safe attribute names reach the serializer.
            attrs = "".join(
                f' {html.escape(k, quote=True)}="{html.escape(v, quote=True)}"'
                for k, v in n["attrs"].items()
                if k.replace("_", "").replace("-", "").isalnum() and k != "href"
            )
            name = html.escape(n["name"])
            indent = "    " * depth
            if n["kind"] == "folder":
                out.append(f"{indent}<DT><H3{attrs}>{name}</H3>")
                out.append(f"{indent}<DL><p>")
                children(n["id"], depth + 1)
                out.append(f"{indent}</DL><p>")
            else:
                url = html.escape(n["url"], quote=True)
                out.append(f'{indent}<DT><A HREF="{url}"{attrs}>{name}</A>')

    children("root", 1)
    if len(seen) != len(nodes):
        raise AppError("integrity_failed", 409)
    out.append("</DL><p>")
    raw = "\n".join(out).encode("utf-8")
    reparsed = parse(raw)
    if structural(reparsed) != structural(nodes):
        raise AppError("integrity_failed", 409)
    return raw


def url_counts(nodes: list[dict]) -> Counter:
    return Counter(n["url"] for n in nodes if n["kind"] == "bookmark")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
