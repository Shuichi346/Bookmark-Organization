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
    original = store.tree(job["project"])
    p["original"] = original
    originals = {n["id"] for n in original}
    p["editable_parents"] = [
        n["id"]
        for n in p["tree"]
        if n["kind"] == "folder"
        and (n["id"] not in originals or n["id"] == job["snapshot"]["destination"])
    ]
    validate(original, p["tree"], p["targets"])
    p["integrity"] = True
    return p


def save_proposal(store: Store, job: str, tree: list[dict], allow: bool) -> str:
    with store.connect() as db:
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
        store.tree(state["project"]), state["snapshot"], state["items"], allow
    )
    return save_proposal(store, job, tree, allow)


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
    return save_proposal(store, p["job"], tree, bool(p["allow_incomplete"]))
