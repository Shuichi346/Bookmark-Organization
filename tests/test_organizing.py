import copy

import pytest
from helpers import ANALYSIS, HTML

from bookmark_organization.bookmarks import parse
from bookmark_organization.integrity import validate
from bookmark_organization.organizing import propose, scope
from bookmark_organization.policy import LEGACY_PROMPT_VERSION, PROMPT_VERSION
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


def purpose_fixture(categories):
    tree, snapshot, old_items = prepared()
    by_id = {node["id"]: node for node in tree}
    seed = by_id[old_items[0]["bookmark"]]
    items = []
    for index, category in enumerate(categories):
        if index < len(old_items):
            identifier = old_items[index]["bookmark"]
        else:
            identifier = f"purpose-bookmark-{index}"
            tree.append(dict(seed, id=identifier, order=len(tree)))
        items.append(
            {
                "bookmark": identifier,
                "state": "complete",
                "retrieval": {"status": "ok"},
                "analysis": dict(
                    ANALYSIS,
                    suggested_name=f"画像の背景を削除｜Tool {index}",
                    candidate_categories=[category],
                ),
                "embedding": {
                    "model": "test",
                    "dimensions": 3,
                    "prompt_version": PROMPT_VERSION,
                    "vector": [1, 0, 0],
                },
            }
        )
    snapshot["targets"] = [item["bookmark"] for item in items]
    snapshot["prompt_version"] = PROMPT_VERSION
    return tree, snapshot, items


def destination_path(tree, identifier, destination):
    by_id = {node["id"]: node for node in tree}
    parts = []
    parent = by_id[identifier]["parent"]
    while parent != destination:
        parts.append(by_id[parent]["name"])
        parent = by_id[parent]["parent"]
    return list(reversed(parts))


def test_purpose_assignments_do_not_depend_on_provider_or_similarity():
    tree, snapshot, items = purpose_fixture(
        ["画像・動画", "画像・動画", "画像・動画", "開発・プログラミング"]
    )
    by_id = {node["id"]: node for node in tree}
    urls = [
        "https://github.com/example/background-remover",
        "https://remove.example/",
        "https://article.example/background-removal",
        "https://github.com/example/image-library",
    ]
    for item, url in zip(items, urls):
        by_id[item["bookmark"]]["url"] = url
    items[1]["embedding"]["vector"] = [0, 1, 0]
    items[2]["embedding"]["vector"] = [0, 0, 1]
    result = propose(tree, snapshot, items, False)
    assert [
        destination_path(result, item["bookmark"], snapshot["destination"])
        for item in items
    ] == [["画像・動画"]] * 3 + [["開発・プログラミング"]]
    assert not any(node["name"] == "要確認" for node in result)


@pytest.mark.parametrize(
    ("categories", "expected"),
    [
        (["画像・動画/画像編集・加工"], [["画像・動画"]]),
        (["画像・動画/画像編集・加工"] * 4, [["画像・動画"]] * 4),
        (
            ["画像・動画/画像編集・加工"] * 2 + ["画像・動画/動画編集・変換"] * 2,
            [["画像・動画"]] * 4,
        ),
        (
            ["画像・動画/画像編集・加工"] * 3 + ["画像・動画/動画編集・変換"] * 2,
            [["画像・動画", "画像編集・加工"]] * 3 + [["画像・動画"]] * 2,
        ),
        (
            ["画像・動画/画像編集・加工"] * 3 + ["画像・動画/動画編集・変換"] * 3,
            [["画像・動画", "画像編集・加工"]] * 3
            + [["画像・動画", "動画編集・変換"]] * 3,
        ),
        (
            ["音楽制作/録音"] * 3 + ["音楽制作"],
            [["音楽制作", "録音"]] * 3 + [["音楽制作"]],
        ),
    ],
)
def test_purpose_subfolders_only_distinguish_populated_sibling_uses(
    categories, expected
):
    tree, snapshot, items = purpose_fixture(categories)
    result = propose(tree, snapshot, items, False)
    assert [
        destination_path(result, item["bookmark"], snapshot["destination"])
        for item in items
    ] == expected
    original_ids = {node["id"] for node in tree}
    created = [node for node in result if node["id"] not in original_ids]
    assert len(created) == len(
        {
            tuple(path[:length])
            for path in expected
            for length in range(1, len(path) + 1)
        }
    )
    assert all(
        any(node["parent"] == folder["id"] for node in result) for folder in created
    )


@pytest.mark.parametrize(
    "categories",
    [
        ["画像・動画/画像編集・加工/背景削除"],
        ["画像・動画", "開発・プログラミング"],
        ["GitHub"],
        ["その他"],
        ["画像・動画/おすすめ"],
        ["画像・動画/.."],
        ["画像・動画/"],
        ["画像・動画\\画像編集"],
    ],
)
def test_purpose_proposal_revalidates_invalid_stored_folder_rules(categories):
    tree, snapshot, items = purpose_fixture(["画像・動画"])
    items[0]["analysis"]["candidate_categories"] = categories
    with pytest.raises(AppError) as invalid:
        propose(tree, snapshot, items, False)
    assert invalid.value.code == "analysis_invalid"


@pytest.mark.parametrize("name", ["背景削除", "削除|Tool", "｜Tool", "便利｜Tool"])
def test_purpose_proposal_revalidates_invalid_stored_names(name):
    tree, snapshot, items = purpose_fixture(["画像・動画"])
    items[0]["analysis"]["suggested_name"] = name
    with pytest.raises(AppError) as invalid:
        propose(tree, snapshot, items, False)
    assert invalid.value.code == "analysis_invalid"


@pytest.mark.parametrize("version", [None, LEGACY_PROMPT_VERSION])
def test_legacy_proposals_preserve_cluster_labels_and_singleton_review(version):
    tree, snapshot, items = purpose_fixture(["旧分類", "別分類", "旧分類"])
    if version is None:
        snapshot.pop("prompt_version")
    else:
        snapshot["prompt_version"] = version
    for item in items:
        item["analysis"]["suggested_name"] = "Legacy name without separator"
        item["embedding"]["prompt_version"] = LEGACY_PROMPT_VERSION
    items[2]["embedding"]["vector"] = [0, 1, 0]
    result = propose(tree, snapshot, items, False)
    assert [
        destination_path(result, item["bookmark"], snapshot["destination"])
        for item in items
    ] == [["旧分類"], ["旧分類"], ["要確認"]]


def test_purpose_export_preserves_duplicates_attributes_failures_and_unselected_nodes():
    tree, snapshot, items = purpose_fixture(["画像・動画"] * 4)
    failed = next(
        item
        for item in items
        if item["retrieval"]["status"] == "ok"
        and next(node for node in tree if node["id"] == item["bookmark"])["name"]
        == "Missing"
    )
    failed["state"] = "retrieval_failed"
    failed["retrieval"]["status"] = "not_found"
    result = propose(tree, snapshot, items, False)
    exported = parse(validate(tree, result, snapshot["targets"]))
    original_urls = [node["url"] for node in tree if node["kind"] == "bookmark"]
    exported_urls = [node["url"] for node in exported if node["kind"] == "bookmark"]
    assert sorted(exported_urls) == sorted(original_urls)
    assert len(original_urls) > len(set(original_urls))
    by_id = {node["id"]: node for node in result}
    for node in tree:
        if node["id"] not in snapshot["targets"]:
            assert by_id[node["id"]] == node
        else:
            assert by_id[node["id"]]["attrs"] == node["attrs"]
    assert by_id[failed["bookmark"]]["name"] == "Missing"
    assert destination_path(result, failed["bookmark"], snapshot["destination"]) == [
        "404"
    ]
