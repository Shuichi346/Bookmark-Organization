import copy
from collections import Counter

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from bookmark_organization.bookmarks import uid
from bookmark_organization.integrity import validate
from bookmark_organization.schemas import AppError, JobRequest

FAILURE_FOLDERS = {
    "not_found": "404",
    "denied": "アクセス制限",
    "timeout": "タイムアウト",
    "connection_failed": "接続失敗",
    "http_error": "HTTPエラー",
    "extraction_failed": "内容取得失敗",
    "unsupported": "未対応リンク",
    "restricted": "取得対象外",
}


def scope(tree: list[dict], request: JobRequest) -> tuple[list[str], list[str], str]:
    by_id = {n["id"]: n for n in tree}
    if request.all:
        return [n["id"] for n in tree if n["kind"] == "bookmark"], [], "root"
    if not request.folders or any(
        f not in by_id or by_id[f]["kind"] != "folder" for f in request.folders
    ):
        raise AppError("invalid_scope")
    selected = set(request.folders)
    normalized = []
    for n in sorted(tree, key=lambda n: n["order"]):
        if n["id"] not in selected:
            continue
        parent = n["parent"]
        while parent != "root" and parent not in selected:
            parent = by_id[parent]["parent"]
        if parent == "root":
            normalized.append(n["id"])
    target = []
    for n in tree:
        if n["kind"] != "bookmark":
            continue
        parent = n["parent"]
        while parent != "root" and parent not in normalized:
            parent = by_id[parent]["parent"]
        if parent in normalized:
            target.append(n["id"])
    destination = request.destination or normalized[0]
    if destination not in normalized:
        raise AppError("invalid_scope")
    return target, normalized, destination


def propose(
    tree: list[dict], snapshot: dict, items: list[dict], allow: bool
) -> list[dict]:
    if len(items) != len(snapshot["targets"]) or {i["bookmark"] for i in items} != set(
        snapshot["targets"]
    ):
        raise AppError("integrity_failed", 409)
    if any(
        i["state"] not in {"complete", "retrieval_failed", "analysis_failed"}
        for i in items
    ):
        raise AppError("job_incomplete", 409)
    if any(i["state"] == "analysis_failed" for i in items) and not allow:
        raise AppError("analysis_incomplete", 409)
    result = copy.deepcopy(tree)
    by_id = {n["id"]: n for n in result}
    destination = snapshot["destination"]
    counter = max((n["order"] for n in tree), default=0) + 1
    folders: dict[str, str] = {}

    def folder(name: str, parent: str) -> str:
        nonlocal counter
        key = f"{parent}/{name}"
        if key in folders:
            return folders[key]
        existing = {n["name"] for n in result if n["parent"] == parent}
        unique = name
        suffix = 2
        while unique in existing:
            unique = f"{name} ({suffix})"
            suffix += 1
        identifier = uid()
        result.append(
            {
                "id": identifier,
                "kind": "folder",
                "name": unique,
                "parent": parent,
                "order": counter,
                "attrs": {},
            }
        )
        counter += 1
        folders[key] = identifier
        return identifier

    if destination == "root":
        destination = folder("整理済み", "root")
    good = [i for i in items if i["state"] == "complete"]
    labels = []
    if good:
        signatures = {
            (
                i["embedding"]["model"],
                i["embedding"]["dimensions"],
                i["embedding"]["prompt_version"],
            )
            for i in good
        }
        if len(signatures) != 1:
            raise AppError("embedding_invalid")
        count = len(good)
        # Budget both the condensed float64 distances and square float64 matrix.
        if count * count * 8 + count * (count - 1) * 4 > 128 * 1024 * 1024:
            raise AppError("memory_budget")
        matrix = np.array([i["embedding"]["vector"] for i in good])
        if count == 1:
            labels = [0]
        else:
            labels = (
                AgglomerativeClustering(
                    n_clusters=None,
                    metric="cosine",
                    linkage="average",
                    distance_threshold=snapshot["settings"]["distance_threshold"],
                )
                .fit_predict(matrix)
                .tolist()
            )
    groups: dict[int, list[dict]] = {}
    for item, label in zip(good, labels):
        groups.setdefault(label, []).append(item)
    for members in groups.values():
        category_counts = Counter(
            c for i in members for c in i["analysis"]["candidate_categories"]
        )
        category = category_counts.most_common(1)[0][0] if category_counts else "要確認"
        if len(good) > 1 and len(members) == 1:
            category = "要確認"
        parent = folder(category, destination)
        for item in members:
            n = by_id[item["bookmark"]]
            n["name"] = item["analysis"]["suggested_name"]
            n["parent"] = parent
            n["order"] = counter
            counter += 1
    for item in items:
        if item["state"] == "complete":
            continue
        status = (item.get("retrieval") or {}).get("status")
        category = FAILURE_FOLDERS.get(status, "要確認")
        n = by_id[item["bookmark"]]
        n["parent"] = folder(category, destination)
        n["order"] = counter
        counter += 1
    validate(tree, result, snapshot["targets"])
    return result
