import copy
import json

import httpx
import pytest
from helpers import FakeAI, FakeFetcher

from bookmark_organization.app import create_app
from bookmark_organization.bookmarks import parse, structural, url_counts
from bookmark_organization.db import Store
from bookmark_organization.integrity import export_scope, validate
from bookmark_organization.jobs import Worker, control, create_job, job_state
from bookmark_organization.proposals import (
    create_proposal,
    edit_proposal,
    get_proposal,
)
from bookmark_organization.schemas import (
    AppError,
    ItemEdit,
    JobRequest,
    OrganizationRules,
)

HTML = b"""<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>
<DT><H3 ADD_DATE="12">A</H3><DL><p>
<DT><A HREF="https://example.com/shared" ADD_DATE="13">Alpha</A></DL>
<DT><H3>B</H3><DL><DT><A HREF="https://example.com/shared">Beta</A></DL>
<DT><H3>C</H3><DL><DT><A HREF="https://example.com/keep">Keep</A></DL>
<DT><H3>F</H3><DL><DT><A HREF="https://example.com/tool">Tool</A></DL>
</DL>"""


class RulesAI(FakeAI):
    observed: list[tuple[OrganizationRules, dict]] = []

    async def analyze(self, bookmark, page):
        self.observed.append((self.rules.model_copy(), dict(bookmark)))
        result = await super().analyze(bookmark, page)
        if self.rules.custom_naming:
            result["suggested_name"] = f"{self.rules.naming_prompt}:{bookmark['name']}"
        if self.rules.custom_folders:
            result["candidate_categories"] = [self.rules.folder_prompt]
        return result


async def finish(store, job):
    await Worker(store, FakeFetcher, RulesAI).process(
        store.one("SELECT * FROM jobs WHERE id=?", (job,))
    )
    assert job_state(store, job)["state"] == "complete"
    return create_proposal(store, job, False)


def folder(tree, name):
    return next(n["id"] for n in tree if n["kind"] == "folder" and n["name"] == name)


def request(tree, name, *, base=None):
    return JobRequest(
        folders=[folder(tree, name)],
        token=f"continuation-{name}",
        base_proposal=base,
        rules=OrganizationRules(
            preset="custom", naming_prompt=f"Name {name}", folder_prompt=f"Group {name}"
        ),
    )


async def test_saved_revisions_continue_a_b_f_with_per_job_rules(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "source.html")
    original = store.tree(project)
    by_id = {n["id"]: n for n in original}
    rules = request(original, "A")
    first_job = create_job(store, project, rules)
    first_snapshot = job_state(store, first_job)["snapshot"]
    rules.rules.naming_prompt = "changed after starting"
    first = await finish(store, first_job)
    p = get_proposal(store, first)
    alpha = next(
        n for n in p["tree"] if n["kind"] == "bookmark" and n["name"].endswith(":Alpha")
    )
    edited = edit_proposal(
        store,
        first,
        alpha["id"],
        ItemEdit(name="My edited Alpha", parent=alpha["parent"]),
    )
    p = get_proposal(store, edited)
    saved_alpha = next(n for n in p["tree"] if n["id"] == alpha["id"])

    # Reopening the data directory recovers the saved proposal, including edits.
    store = Store(tmp_path)
    assert store.latest_proposal(project) == edited
    second_job = create_job(store, project, request(p["tree"], "B", base=edited))
    assert job_state(store, second_job)["snapshot"]["base_tree"] == p["tree"]
    second = await finish(store, second_job)
    p = get_proposal(store, second)
    assert next(n for n in p["tree"] if n["id"] == alpha["id"]) == saved_alpha
    saved_beta = next(n for n in p["tree"] if n.get("name") == "Name B:Beta")

    # Older API clients may omit a base; the latest saved result is preserved.
    third_job = create_job(store, project, request(p["tree"], "F"))
    third_snapshot = job_state(store, third_job)["snapshot"]
    assert third_snapshot["base_proposal"] == second
    third = await finish(store, third_job)
    p = get_proposal(store, third)
    final = {n["id"]: n for n in p["tree"]}
    assert final[alpha["id"]] == saved_alpha
    assert final[saved_beta["id"]] == saved_beta
    assert next(n for n in final.values() if n.get("name") == "Name F:Tool")
    for n in original:
        if n["kind"] == "folder" or n["name"] == "Keep":
            assert final[n["id"]] == n
    assert set(by_id).issubset(final)
    assert url_counts(original) == url_counts(p["tree"])
    assert len(p["cumulative_targets"]) == 3
    exported = validate(p["import_original"], p["tree"], p["cumulative_targets"])
    assert structural(parse(exported)) == structural(p["tree"])
    partial = parse(
        export_scope(
            p["import_original"], p["tree"], p["cumulative_targets"], changed=True
        )
    )
    assert url_counts(partial) == url_counts(
        [n for n in p["tree"] if n["id"] in p["cumulative_targets"]]
    )
    assert not any(n["name"] in {"C", "Keep"} for n in partial)
    assert {"My edited Alpha", "Name B:Beta", "Name F:Tool"}.issubset(
        n["name"] for n in partial
    )
    assert store.tree(project) == original
    assert (
        store.one("SELECT original FROM projects WHERE id=?", (project,))["original"]
        == HTML
    )
    assert job_state(store, first_job)["snapshot"] == first_snapshot
    assert first_snapshot["rules"]["naming_prompt"] == "Name A"

    # Reimport starts clean while the migrated project's jobs/results remain saved.
    with store.connect() as db:
        db.execute("CREATE UNIQUE INDEX legacy_hash ON projects(hash)")
    store = Store(tmp_path)
    fresh = store.import_html(HTML, "source.html")
    assert fresh != project
    assert store.latest_proposal(fresh) is None
    assert store.rows("SELECT id FROM jobs WHERE project=?", (fresh,)) == []
    assert store.latest_proposal(project) == third
    assert get_proposal(store, third)["tree"] == p["tree"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tmp_path)),
        base_url="http://testserver",
    ) as client:
        for mode, expected in [
            ("all", exported),
            (
                "changed",
                export_scope(
                    p["import_original"],
                    p["tree"],
                    p["cumulative_targets"],
                    changed=True,
                ),
            ),
        ]:
            response = await client.get(f"/api/proposals/{third}/export?scope={mode}")
            assert response.status_code == 200
            assert response.content == expected
        assert (
            await client.get(f"/api/proposals/{third}/export?scope=invalid")
        ).status_code == 422

    # Generated folders can be selected again; analysis receives the saved name
    # and folder path rather than the unchanged import's values.
    again = request(p["tree"], "Group A", base=third)
    again_job = create_job(store, project, again)
    await finish(store, again_job)
    observed_rules, observed_bookmark = RulesAI.observed[-1]
    assert observed_rules.naming_prompt == "Name Group A"
    assert observed_bookmark["name"] == "My edited Alpha"
    assert observed_bookmark["original_folder_path"] == "A / Group A"


async def test_stale_bases_and_edits_cannot_replace_newer_results(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "source.html")
    first_job = create_job(store, project, request(store.tree(project), "A"))
    first = await finish(store, first_job)
    p = get_proposal(store, first)
    bid = p["targets"][0]
    bookmark = next(n for n in p["tree"] if n["id"] == bid)
    edit = ItemEdit(name="Saved edit", parent=bookmark["parent"])
    latest = edit_proposal(store, first, bid, edit)
    with pytest.raises(AppError, match="stale_proposal"):
        edit_proposal(store, first, bid, edit)
    with pytest.raises(AppError, match="stale_proposal"):
        create_job(store, project, request(p["tree"], "B", base=first))

    job = create_job(store, project, request(p["tree"], "B", base=latest))
    # Repeated submission returns the same immutable job even after newer edits.
    assert create_job(store, project, request(p["tree"], "B", base=latest)) == job
    with pytest.raises(AppError, match="job_conflict"):
        edit_proposal(store, latest, bid, edit)
    second = await finish(store, job)
    with pytest.raises(AppError, match="stale_proposal"):
        edit_proposal(store, latest, bid, edit)
    assert store.latest_proposal(project) == second


async def test_cumulative_integrity_rejects_prior_scope_or_import_corruption(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "source.html")
    first_job = create_job(store, project, request(store.tree(project), "A"))
    first = await finish(store, first_job)
    first_tree = get_proposal(store, first)["tree"]
    second_job = create_job(store, project, request(first_tree, "B", base=first))
    second = await finish(store, second_job)
    p = get_proposal(store, second)
    tree = copy.deepcopy(p["tree"])
    alpha = next(n for n in tree if n.get("name") == "Name A:Alpha")
    alpha["name"] = "Accidentally changed previous result"
    with store.connect() as db:
        db.execute(
            "UPDATE proposal_versions SET tree=? WHERE id=?", (json.dumps(tree), second)
        )
    with pytest.raises(AppError, match="integrity_failed"):
        get_proposal(store, second)

    # Even matching corruption in the saved base cannot alter imported URLs.
    snapshot = job_state(store, second_job)["snapshot"]
    for nodes in [tree, snapshot["base_tree"]]:
        n = next(n for n in nodes if n["id"] == alpha["id"])
        n["name"] = "Name A:Alpha"
        n["url"] = "https://example.com/corrupted"
    with store.connect() as db:
        db.execute(
            "UPDATE proposal_versions SET tree=? WHERE id=?", (json.dumps(tree), second)
        )
        db.execute(
            "UPDATE jobs SET snapshot=? WHERE id=?", (json.dumps(snapshot), second_job)
        )
    with pytest.raises(AppError, match="integrity_failed"):
        get_proposal(store, second)


async def test_published_jobs_and_superseded_snapshots_cannot_retry(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "source.html")
    original = store.tree(project)
    unpublished = create_job(store, project, request(original, "A"))
    await Worker(store, FakeFetcher, RulesAI).process(
        store.one("SELECT * FROM jobs WHERE id=?", (unpublished,))
    )
    assert not job_state(store, unpublished)["has_proposal"]
    published = create_job(store, project, request(original, "B"))
    latest = await finish(store, published)
    before = job_state(store, published)
    assert before["has_proposal"]
    with pytest.raises(AppError, match="job_already_proposed"):
        control(store, published, "retry-failed")
    assert job_state(store, published) == before
    with pytest.raises(AppError, match="stale_proposal"):
        control(store, unpublished, "retry-failed")
    assert job_state(store, unpublished)["state"] == "complete"
    # A paused snapshot from an older revision must not be resumed either.
    with store.connect() as db:
        db.execute("UPDATE jobs SET state='paused' WHERE id=?", (unpublished,))
    with pytest.raises(AppError, match="stale_proposal"):
        control(store, unpublished, "resume")
    control(store, unpublished, "cancel")
    child = create_job(
        store, project, request(get_proposal(store, latest)["tree"], "F", base=latest)
    )
    control(store, child, "pause")
    control(store, child, "resume")
    assert job_state(store, child)["state"] == "running"


async def test_completed_child_proposal_must_be_saved_before_editing_base(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "source.html")
    first_job = create_job(store, project, request(store.tree(project), "A"))
    first = await finish(store, first_job)
    p = get_proposal(store, first)
    bid = p["targets"][0]
    bookmark = next(n for n in p["tree"] if n["id"] == bid)
    edit = ItemEdit(name="Changed parent result", parent=bookmark["parent"])
    second_job = create_job(store, project, request(p["tree"], "B", base=first))
    await Worker(store, FakeFetcher, RulesAI).process(
        store.one("SELECT * FROM jobs WHERE id=?", (second_job,))
    )
    assert job_state(store, second_job)["state"] == "complete"
    with pytest.raises(AppError, match="pending_proposal"):
        edit_proposal(store, first, bid, edit)
    assert store.latest_proposal(project) == first
    second = create_proposal(store, second_job, False)
    assert store.latest_proposal(project) == second
    assert (
        next(n for n in get_proposal(store, second)["tree"] if n["id"] == bid)
        == bookmark
    )
