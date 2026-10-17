from bookmark_organization.bookmarks import export, url_counts
from bookmark_organization.schemas import AppError


def validate(original: list[dict], proposed: list[dict], targets: list[str]) -> bytes:
    old = {n["id"]: n for n in original}
    new = {n["id"]: n for n in proposed}
    old_bookmarks = {n["id"] for n in original if n["kind"] == "bookmark"}
    new_bookmarks = {n["id"] for n in proposed if n["kind"] == "bookmark"}
    if (
        len(new) != len(proposed)
        or old_bookmarks != new_bookmarks
        or url_counts(original) != url_counts(proposed)
        or not set(old).issubset(new)
        or not set(targets).issubset(old_bookmarks)
    ):
        raise AppError("integrity_failed", 409)
    selected = set(targets)
    for key, before in old.items():
        after = new[key]
        if before["kind"] == "folder" or key not in selected:
            if before != after:
                raise AppError("integrity_failed", 409)
        elif any(
            before.get(field) != after.get(field)
            for field in ("id", "kind", "url", "attrs")
        ):
            raise AppError("integrity_failed", 409)
    # Ordering among untouched siblings must remain invariant.
    for parent in {n["parent"] for n in original}:
        untouched = [
            n["id"]
            for n in sorted(original, key=lambda n: n["order"])
            if n["parent"] == parent and n["id"] not in selected
        ]
        current = [
            n["id"]
            for n in sorted(proposed, key=lambda n: n["order"])
            if n["parent"] == parent and n["id"] in untouched
        ]
        if current != untouched:
            raise AppError("integrity_failed", 409)
    return export(proposed)


def export_scope(
    original: list[dict], proposed: list[dict], targets: list[str], *, changed: bool
) -> bytes:
    # Always validate the complete proposal before excluding untouched content.
    raw = validate(original, proposed, targets)
    if not changed:
        return raw
    nodes = {n["id"]: n for n in proposed}
    included = set(targets)
    for identifier in targets:
        parent = nodes[identifier]["parent"]
        while parent != "root" and parent not in included:
            included.add(parent)
            parent = nodes[parent]["parent"]
    # Ancestors retain their attributes and order, but unrelated siblings are
    # omitted. Targeted failures stay included even if their names did not change.
    return export([n for n in proposed if n["id"] in included])
