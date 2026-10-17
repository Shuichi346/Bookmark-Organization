import copy
import json

from bookmark_organization.bookmarks import uid
from bookmark_organization.db import Store
from bookmark_organization.integrity import validate
from bookmark_organization.jobs import job_state
from bookmark_organization.organizing import propose
from bookmark_organization.schemas import AppError, ItemEdit


def get_proposal(store: Store, identifier: str) -> dict:
    p = store.one("SELECT * FROM proposal_versions WHERE id=?", (identifier,))
    p["tree"] = json.loads(p["tree"])
    job = job_state(store, p["job"])
    p["project"] = job["project"]
    p["targets"] = job["snapshot"]["targets"]
    p["items"] = job["items"]
    original = store.job_tree(job["project"], job["snapshot"])
    p["original"] = original
    p["base_proposal"] = job["snapshot"].get("base_proposal")
    p["import_original"] = store.tree(job["project"])
    p["cumulative_targets"] = job["snapshot"].get("cumulative_targets", p["targets"])
    originals = {n["id"] for n in original}
    p["editable_parents"] = [
        n["id"]
        for n in p["tree"]
        if n["kind"] == "folder"
        and (n["id"] not in originals or n["id"] == job["snapshot"]["destination"])
    ]
    validate(original, p["tree"], p["targets"])
    # The local gate preserves the previous revision; this gate also checks the
    # full chain against immutable bookmark identities and duplicate URLs.
    validate(p["import_original"], p["tree"], p["cumulative_targets"])
    p["integrity"] = True
    return p


def save_proposal(
    store: Store,
    job: str,
    tree: list[dict],
    allow: bool,
    *,
    expected_proposal: str | None = None,
) -> str:
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        state = job_state(store, job)
        if state["state"] != "complete":
            raise AppError("job_incomplete", 409)
        if store.latest_proposal(state["project"]) != expected_proposal:
            raise AppError("stale_proposal", 409)
        active = db.execute(
            "SELECT id FROM jobs WHERE project=? AND state IN ('running','paused')",
            (state["project"],),
        ).fetchone()
        if active:
            raise AppError("job_conflict", 409)
        is_edit = bool(
            db.execute(
                "SELECT id FROM proposal_versions WHERE id=? AND job=?",
                (expected_proposal, job),
            ).fetchone()
        )
        if is_edit:
            unpublished = db.execute(
                "SELECT j.snapshot FROM jobs j WHERE j.project=? AND j.state='complete' "
                "AND NOT EXISTS(SELECT 1 FROM proposal_versions p WHERE p.job=j.id)",
                (state["project"],),
            )
            if any(
                json.loads(child["snapshot"]).get("base_proposal") == expected_proposal
                for child in unpublished
            ):
                raise AppError("pending_proposal", 409)
        snapshot = state["snapshot"]
        validate(store.job_tree(state["project"], snapshot), tree, snapshot["targets"])
        validate(
            store.tree(state["project"]),
            tree,
            snapshot.get("cumulative_targets", snapshot["targets"]),
        )
        version = db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM proposal_versions WHERE job=?",
            (job,),
        ).fetchone()[0]
        identifier = uid()
        db.execute(
            "INSERT INTO proposal_versions VALUES(?,?,?,?,?)",
            (identifier, job, version, json.dumps(tree), int(allow)),
        )
        db.executemany(
            "INSERT INTO proposal_items VALUES(?,?,?)",
            [
                (identifier, n["id"], json.dumps(n))
                for n in tree
                if n["kind"] == "bookmark"
            ],
        )
    return identifier


def create_proposal(store: Store, job: str, allow: bool) -> str:
    state = job_state(store, job)
    if state["state"] != "complete":
        raise AppError("job_incomplete", 409)
    existing = store.rows(
        "SELECT id FROM proposal_versions WHERE job=? ORDER BY version DESC LIMIT 1",
        (job,),
    )
    if existing:
        return existing[0]["id"]
    tree = propose(
        store.job_tree(state["project"], state["snapshot"]),
        state["snapshot"],
        state["items"],
        allow,
    )
    return save_proposal(
        store,
        job,
        tree,
        allow,
        expected_proposal=state["snapshot"].get("base_proposal"),
    )


def edit_proposal(store: Store, identifier: str, bid: str, edit: ItemEdit) -> str:
    p = get_proposal(store, identifier)
    if bid not in p["targets"] or edit.parent not in p["editable_parents"]:
        raise AppError("invalid_scope")
    tree = copy.deepcopy(p["tree"])
    for n in tree:
        if n["id"] == bid:
            n["name"] = edit.name
            if n["parent"] != edit.parent:
                n["parent"] = edit.parent
                n["order"] = max(m["order"] for m in tree) + 1
    validate(p["original"], tree, p["targets"])
    return save_proposal(
        store,
        p["job"],
        tree,
        bool(p["allow_incomplete"]),
        expected_proposal=identifier,
    )
