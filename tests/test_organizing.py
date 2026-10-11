import copy

import pytest
from helpers import ANALYSIS, HTML

from bookmark_organization.bookmarks import parse
from bookmark_organization.integrity import validate
from bookmark_organization.organizing import propose, scope
from bookmark_organization.schemas import AppError, JobRequest, Settings


def prepared():
    tree = parse(HTML)
    folders = [n["id"] for n in tree if n["name"] in {"A", "B", "Nested"}]
    targets, normalized, destination = scope(
        tree, JobRequest(folders=folders, token="test-token")
    )
    snapshot = {
        "targets": targets,
        "folders": normalized,
        "destination": destination,
        "settings": Settings().model_dump(),
    }
    items = []
    for n in tree:
        if n["id"] not in targets:
            continue
        missing = "missing" in n["url"]
        items.append(
            {
                "bookmark": n["id"],
                "state": "retrieval_failed" if missing else "complete",
                "retrieval": {"status": "not_found" if missing else "ok"},
                "analysis": ANALYSIS,
                "embedding": {
                    "model": "test",
                    "dimensions": 3,
                    "prompt_version": "test",
                    "vector": [1, 0, 0],
                },
            }
        )
    return tree, snapshot, items


def test_overlapping_multifolder_organization_and_out_of_scope():
    tree, snapshot, items = prepared()
    assert len(snapshot["folders"]) == 2
    assert len(snapshot["targets"]) == 4
    result = propose(tree, snapshot, items, False)
    assert validate(tree, result, snapshot["targets"])
    for n in tree:
        if n["id"] not in snapshot["targets"]:
            assert n == next(r for r in result if r["id"] == n["id"])
    missing = next(n for n in tree if n["name"] == "Missing")
    updated = next(n for n in result if n["id"] == missing["id"])
    assert updated["name"] == "Missing"
    assert next(n for n in result if n["id"] == updated["parent"])["name"] == "404"
    assert all(
        n["parent"] == snapshot["destination"]
        for n in result
        if n["id"] not in {m["id"] for m in tree}
    )


def test_all_single_scope_and_explicit_incomplete_gate():
    tree, snapshot, items = prepared()
    a = next(n["id"] for n in tree if n["name"] == "A")
    assert len(scope(tree, JobRequest(folders=[a], token="test-token"))[0]) == 2
    assert len(scope(tree, JobRequest(all=True, token="test-token"))[0]) == 6
    items[0]["state"] = "analysis_failed"
    with pytest.raises(AppError) as error:
        propose(tree, snapshot, items, False)
    assert error.value.code == "analysis_incomplete"
    result = propose(tree, snapshot, items, True)
    assert any(n["name"] == "要確認" for n in result)


def test_loss_duplication_folder_mutation_and_incompatible_embeddings():
    tree, snapshot, items = prepared()
    result = propose(tree, snapshot, items, False)
    for mutate in ("loss", "duplicate", "folder", "outside"):
        bad = copy.deepcopy(result)
        if mutate == "loss":
            bad.remove(next(n for n in bad if n["kind"] == "bookmark"))
        elif mutate == "duplicate":
            bad.append(copy.deepcopy(next(n for n in bad if n["kind"] == "bookmark")))
        elif mutate == "folder":
            bad[0]["name"] = "Changed"
        else:
            next(n for n in bad if n["name"] == "Keep")["name"] = "Changed"
        with pytest.raises(AppError):
            validate(tree, bad, snapshot["targets"])
    items[1]["embedding"]["model"] = "different"
    with pytest.raises(AppError):
        propose(tree, snapshot, items, False)


def test_memory_budget_and_missing_results_are_rejected():
    tree, snapshot, items = prepared()
    with pytest.raises(AppError) as missing:
        propose(tree, snapshot, items[:-1], False)
    assert missing.value.code == "integrity_failed"
    original = next(n for n in tree if n["kind"] == "bookmark")
    big_tree = [n for n in tree if n["kind"] == "folder"]
    big_items = []
    for index in range(4000):
        node = dict(original, id=str(index))
        big_tree.append(node)
        big_items.append(dict(items[0], bookmark=str(index)))
    snapshot["targets"] = [item["bookmark"] for item in big_items]
    with pytest.raises(AppError) as memory:
        propose(big_tree, snapshot, big_items, False)
    assert memory.value.code == "memory_budget"
