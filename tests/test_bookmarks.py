import copy

import pytest
from helpers import HTML

from bookmark_organization.bookmarks import export, parse, sha, structural
from bookmark_organization.db import Store
from bookmark_organization.integrity import validate
from bookmark_organization.schemas import AppError


def test_roundtrip_duplicates_original_and_special_characters(tmp_path):
    raw = HTML.replace(b"Alpha &amp; One", "日本語 &amp; &quot;Quote&quot;".encode())
    store = Store(tmp_path)
    project = store.import_html(raw, "sample.html")
    assert store.import_html(raw, "again.html") == project
    record = store.one("SELECT * FROM projects WHERE id=?", (project,))
    assert record["original"] == raw
    assert record["hash"] == sha(raw)
    nodes = store.tree(project)
    assert structural(parse(export(nodes))) == structural(nodes)
    assert sum(n["kind"] == "bookmark" for n in nodes) == 6
    assert len({n["id"] for n in nodes}) == len(nodes)
    assert len([n for n in nodes if n.get("url") == "https://example.com/alpha"]) == 2
    assert any(n["name"] == "Empty" for n in nodes)


def test_same_folder_names_unclosed_anchor_and_invalid_schemes():
    raw = b'<DL><DT><H3>X</H3><DL><A HREF="not a url">One<DT><A HREF="file:///tmp/x">Two</DL><DT><H3>X</H3><DL></DL></DL>'
    tree = parse(raw)
    assert len({n["id"] for n in tree if n["kind"] == "folder"}) == 2
    assert structural(parse(export(tree))) == structural(tree)


@pytest.mark.parametrize(
    "raw", [b"<DL><A>No href</A></DL>", b"<html>Wrong</html>", b"\xff"]
)
def test_invalid_import_is_atomic(tmp_path, raw):
    store = Store(tmp_path)
    with pytest.raises(AppError):
        store.import_html(raw, "bad.html")
    assert store.rows("SELECT id FROM projects") == []


def test_id_loss_and_duplication_are_detected_even_with_duplicate_url():
    tree = parse(HTML)
    bookmarks = [n for n in tree if n["kind"] == "bookmark"]
    targets = [n["id"] for n in bookmarks]
    bad = copy.deepcopy(tree)
    duplicate = next(n for n in bad if n["name"] == "Duplicate")
    bad.remove(duplicate)
    alpha = next(n for n in bad if n.get("url") == duplicate["url"])
    bad.append(copy.deepcopy(alpha))
    with pytest.raises(AppError):
        validate(tree, bad, targets)
