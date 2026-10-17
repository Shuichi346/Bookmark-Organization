import copy
import json
import sqlite3

import pytest
from helpers import HTML

from bookmark_organization.bookmarks import export, parse, sha, structural
from bookmark_organization.db import Store
from bookmark_organization.integrity import export_scope, validate
from bookmark_organization.schemas import AppError


def test_roundtrip_duplicates_original_and_special_characters(tmp_path):
    raw = HTML.replace(b"Alpha &amp; One", "日本語 &amp; &quot;Quote&quot;".encode())
    store = Store(tmp_path)
    project = store.import_html(raw, "sample.html")
    again = store.import_html(raw, "sample.html")
    assert again != project
    assert structural(store.tree(again)) == structural(store.tree(project))
    assert {n["id"] for n in store.tree(again)}.isdisjoint(
        n["id"] for n in store.tree(project)
    )
    assert store.latest_proposal(again) is None
    record = store.one("SELECT * FROM projects WHERE id=?", (project,))
    assert record["original"] == raw
    assert record["hash"] == sha(raw)
    nodes = store.tree(project)
    assert structural(parse(export(nodes))) == structural(nodes)
    assert sum(n["kind"] == "bookmark" for n in nodes) == 6
    assert len({n["id"] for n in nodes}) == len(nodes)
    assert len([n for n in nodes if n.get("url") == "https://example.com/alpha"]) == 2
    assert any(n["name"] == "Empty" for n in nodes)


def test_legacy_hash_constraint_migrates_without_losing_imports(tmp_path):
    tree = parse(HTML)
    with sqlite3.connect(tmp_path / "bookmarks.sqlite3") as db:
        db.execute("""CREATE TABLE projects (
            id TEXT PRIMARY KEY, hash TEXT UNIQUE, original BLOB, tree TEXT,
            filename TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)""")
        db.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?,?)",
            ("saved", sha(HTML), HTML, json.dumps(tree), "saved.html", "2026-10-01"),
        )
    store = Store(tmp_path)
    before = store.one("SELECT rowid,* FROM projects WHERE id='saved'")
    fresh = store.import_html(HTML, "saved.html")
    assert fresh != "saved"
    assert store.tree("saved") == tree
    assert before["original"] == HTML
    assert before["created"] == "2026-10-01"
    reopened = Store(tmp_path)
    assert reopened.one("SELECT rowid,* FROM projects WHERE id='saved'") == before
    assert reopened.import_html(HTML, "renamed.html") not in {"saved", fresh}


def test_changed_export_uses_ids_and_ancestor_closure_including_root_and_failures():
    tree = parse(HTML)
    duplicate = next(n for n in tree if n["name"] == "Duplicate")
    mail = next(n for n in tree if n["name"] == "Mail")
    missing = next(n for n in tree if n["name"] == "Missing")
    # These targeted failure/unchanged entries still belong to the organized block.
    targets = [duplicate["id"], mail["id"], missing["id"]]
    raw = export_scope(tree, tree, targets, changed=True)
    subset = parse(raw)
    assert {n["name"] for n in subset} == {"B", "Duplicate", "Missing", "Mail"}
    assert structural(subset) == structural(
        [n for n in tree if n["id"] in {*targets, duplicate["parent"]}]
    )
    assert export_scope(tree, tree, targets, changed=False) == export(tree)
    # A corrupt item outside the partial range must still block the download.
    bad = copy.deepcopy(tree)
    next(n for n in bad if n["name"] == "Keep")["name"] = "Corrupted"
    with pytest.raises(AppError, match="integrity_failed"):
        export_scope(tree, bad, targets, changed=True)


def test_changed_export_preserves_duplicate_urls_and_same_named_folder_paths():
    tree = parse(b"""<DL><H3>X</H3><DL><A HREF="https://example.com">One</A>
        </DL><H3>X</H3><DL><A HREF="https://example.com">Two</A>
        <A HREF="https://example.com/keep">Keep</A></DL></DL>""")
    targets = [n["id"] for n in tree if n["name"] in {"One", "Two"}]
    subset = parse(export_scope(tree, tree, targets, changed=True))
    assert [n["name"] for n in subset if n["kind"] == "folder"] == ["X", "X"]
    assert [n["url"] for n in subset if n["kind"] == "bookmark"] == [
        "https://example.com",
        "https://example.com",
    ]


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
