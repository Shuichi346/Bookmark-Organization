import asyncio
import hmac
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bookmark_organization.db import Store
from bookmark_organization.i18n import CATALOGS, locale, translate
from bookmark_organization.integrity import validate
from bookmark_organization.jobs import Worker, control, create_job, job_state
from bookmark_organization.llm import LocalAI
from bookmark_organization.proposals import create_proposal, edit_proposal, get_proposal
from bookmark_organization.schemas import (
    AppError,
    ItemEdit,
    JobRequest,
    ProposalRequest,
    SettingsUpdate,
)

PACKAGE = Path(__file__).parent


def create_app(directory: Path | None = None, worker_factory=Worker) -> FastAPI:
    store = Store(directory or Path(os.environ.get("BOOKMARK_DATA_DIR", "data")))
    worker = worker_factory(store)

    @asynccontextmanager
    async def lifespan(application):
        worker.recover()
        task = asyncio.create_task(worker.run())
        yield
        worker.stopping = True
        worker.wake.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    application = FastAPI(lifespan=lifespan)
    application.state.store = store
    application.state.worker = worker
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )
    templates = Jinja2Templates(directory=str(PACKAGE / "templates"))
    static = PACKAGE / "static"
    if static.exists():
        application.mount("/static", StaticFiles(directory=static), name="static")

    @application.middleware("http")
    async def security(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            cookie = request.cookies.get("csrf", "")
            token = request.headers.get("x-csrf-token", "")
            origin = request.headers.get("origin")
            if (
                not cookie
                or not hmac.compare_digest(cookie, token)
                or (origin and urlsplit(origin).netloc != request.headers.get("host"))
            ):
                return JSONResponse({"code": "csrf_failed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @application.exception_handler(AppError)
    async def app_error(request: Request, error: AppError):
        return JSONResponse({"code": error.code}, status_code=error.status)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse({"code": "validation_error"}, status_code=422)

    def context(request: Request):
        code = locale(
            request.cookies.get("language"), request.headers.get("accept-language")
        )
        return {
            "request": request,
            "lang": code,
            "t": lambda key, **values: translate(code, key, **values),
            "messages": CATALOGS[code],
        }

    @application.get("/health")
    async def health():
        return {"status": "ok"}

    @application.get("/")
    async def home(
        request: Request, project: str | None = None, proposal: str | None = None
    ):
        ctx = context(request)
        projects = store.rows(
            "SELECT id,filename FROM projects ORDER BY created DESC,rowid DESC"
        )
        if not project and projects:
            project = projects[0]["id"]
        jobs = (
            store.rows(
                "SELECT id FROM jobs WHERE project=? ORDER BY created DESC,rowid DESC LIMIT 1",
                (project,),
            )
            if project
            else []
        )
        job = job_state(store, jobs[0]["id"]) if jobs else None
        if not proposal and project:
            proposal = store.latest_proposal(project)
        p = get_proposal(store, proposal) if proposal else None
        if p and p["project"] != project:
            raise AppError("invalid_scope")
        tree = p["tree"] if p else store.tree(project) if project else []
        rules = job["snapshot"].get("rules", {}) if job else {}
        token = request.cookies.get("csrf") or secrets.token_urlsafe(32)
        manifest_path = static / ".vite" / "manifest.json"
        if not manifest_path.exists():
            return Response(
                "Build assets first: npm ci && npm run build", status_code=503
            )
        manifest = json.loads(manifest_path.read_text())["frontend/main.ts"]
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                **ctx,
                "project": project,
                "tree": tree,
                "job": job,
                "proposal": p,
                "rules": rules,
                "csrf": token,
                "settings": store.public_settings(),
                "preference": request.cookies.get("language", "auto"),
                "js": manifest["file"],
                "css": manifest.get("css", []),
                "total": sum(n["kind"] == "bookmark" for n in tree),
            },
        )
        response.set_cookie("csrf", token, httponly=True, samesite="strict", path="/")
        return response

    @application.post("/api/language")
    async def language(request: Request):
        value = (await request.json()).get("preference", "auto")
        if value not in {"auto", "en", "ja"}:
            value = "auto"
        response = JSONResponse({"preference": value})
        response.set_cookie(
            "language", value, max_age=31536000, samesite="strict", path="/"
        )
        return response

    @application.post("/api/projects/import")
    async def import_html(file: UploadFile = File(...)):
        raw = await file.read(25 * 1024 * 1024 + 1)
        return {"id": store.import_html(raw, file.filename or "bookmarks.html")}

    @application.get("/api/projects/{project}/tree")
    async def project_tree(project: str):
        return {"id": project, "nodes": store.tree(project)}

    @application.get("/api/projects/{project}/original")
    async def original(project: str):
        row = store.one("SELECT original FROM projects WHERE id=?", (project,))
        return Response(
            row["original"],
            media_type="text/html",
            headers={
                "Content-Disposition": 'attachment; filename="original-bookmarks.html"'
            },
        )

    @application.get("/api/settings")
    async def settings():
        return store.public_settings()

    @application.put("/api/settings")
    async def save_settings(values: SettingsUpdate):
        store.save_openrouter_api_key(values.openrouter_api_key.get_secret_value())
        store.save_settings(values.settings())
        return store.public_settings()

    @application.post("/api/settings/probe")
    async def probe(values: SettingsUpdate):
        ai = LocalAI(
            values.settings(),
            api_key=values.openrouter_api_key.get_secret_value()
            or store.openrouter_api_key(),
        )
        try:
            return {
                "generation": await ai.models(values.generation),
                "embedding": await ai.models(values.embedding, role="embedding"),
            }
        finally:
            await ai.close()

    @application.post("/api/projects/{project}/jobs")
    async def start(project: str, values: JobRequest):
        identifier = create_job(store, project, values)
        worker.wake.set()
        return {"id": identifier}

    @application.get("/api/jobs/{identifier}")
    async def status(identifier: str):
        return job_state(store, identifier)

    @application.post("/api/jobs/{identifier}/{action}")
    async def job_action(
        identifier: str, action: str, values: ProposalRequest | None = None
    ):
        if action == "proposal":
            return {
                "id": create_proposal(
                    store, identifier, bool(values and values.allow_incomplete)
                )
            }
        if action not in {"pause", "resume", "retry-failed", "cancel"}:
            raise AppError("not_found", 404)
        control(store, identifier, action)
        if action == "cancel":
            worker.cancel(identifier)
        worker.wake.set()
        return {"id": identifier}

    @application.get("/api/proposals/{identifier}")
    async def get_result(identifier: str):
        return get_proposal(store, identifier)

    @application.patch("/api/proposals/{identifier}/items/{bid}")
    async def edit_result(identifier: str, bid: str, values: ItemEdit):
        saved = edit_proposal(store, identifier, bid, values)
        return {"id": saved, "tree": get_proposal(store, saved)["tree"]}

    @application.get("/api/proposals/{identifier}/export")
    async def download(identifier: str):
        p = get_proposal(store, identifier)
        raw = validate(p["original"], p["tree"], p["targets"])
        return Response(
            raw,
            media_type="text/html",
            headers={
                "Content-Disposition": 'attachment; filename="organized-bookmarks.html"'
            },
        )

    @application.get("/ui/jobs/{identifier}")
    async def job_fragment(request: Request, identifier: str):
        return templates.TemplateResponse(
            request=request,
            name="progress.html",
            context={**context(request), "job": job_state(store, identifier)},
        )

    @application.get("/ui/proposals/{identifier}")
    async def proposal_fragment(
        request: Request, identifier: str, q: str = "", status: str = "", page: int = 1
    ):
        p = get_proposal(store, identifier)
        old = {n["id"]: n for n in p["original"]}
        after = {n["id"]: n for n in p["tree"]}
        items = {i["bookmark"]: i for i in p["items"]}

        def path(nodes, parent):
            parts = []
            while parent != "root":
                n = nodes[parent]
                parts.append(n["name"])
                parent = n["parent"]
            return " / ".join(reversed(parts)) or translate(
                context(request)["lang"], "root"
            )

        rows = []
        for bid in p["targets"]:
            before, proposed, item = old[bid], after[bid], items[bid]
            if (
                q.lower()
                not in (before["name"] + proposed["name"] + before["url"]).lower()
            ):
                continue
            if status and item["state"] != status:
                continue
            rows.append(
                {
                    "id": bid,
                    "before": before,
                    "after": proposed,
                    "item": item,
                    "old_path": path(old, before["parent"]),
                    "new_path": path(after, proposed["parent"]),
                }
            )
        pages = max(1, (len(rows) + 24) // 25)
        page = max(1, min(page, pages))
        return templates.TemplateResponse(
            request=request,
            name="comparison.html",
            context={
                **context(request),
                "proposal": p,
                "rows": rows[(page - 1) * 25 : page * 25],
                "page": page,
                "pages": pages,
                "parents": [(f, path(after, f)) for f in p["editable_parents"]],
            },
        )

    @application.get("/ui")
    async def ui_redirect():
        return RedirectResponse("/")

    return application


def main():
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=int(os.environ.get("BOOKMARK_PORT", "8765")),
    )


if __name__ == "__main__":
    main()
