"""HTTP API for the browser UI, built on FastAPI.

The server only ever listens on the loopback address. Three checks protect it:

  * the Host header must be one of the loopback names for this port, which
    stops DNS-rebinding from another website;
  * every ``/api/`` call needs the random token that is only handed to the
    ReData page this engine serves;
  * responses carry a strict Content-Security-Policy.

Errors are always ``{"error": "..."}`` so the page can show them as they are.
"""

import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from . import __version__ as VERSION
from .pipeline import PipelineError
from .util import UserError

MAX_JSON_BODY = 10 * 1024 * 1024
TOKEN_HEADER = "x-redata-token"

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".woff2": "font/woff2",
}

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
}


# --------------------------------------------------------------------------
# request bodies
# --------------------------------------------------------------------------
# The page sends loosely filled JSON objects, so every field is optional and
# the engine applies its own defaults and limits. Unknown fields are ignored.

class StagePathRequest(BaseModel):
    path: Optional[str] = None


class StageRequest(BaseModel):
    stage: Optional[str] = None


class PreviewRequest(StageRequest):
    sheet: Optional[int] = 0


class LoadRequest(StageRequest):
    header: bool = True
    names: Optional[List[Optional[str]]] = None
    sheet: Optional[int] = 0


class RowsRequest(BaseModel):
    offset: Optional[int] = 0
    limit: Optional[int] = 150
    sort: Optional[str] = None
    dir: Optional[int] = 1
    column: Optional[str] = None
    query: Any = ""


class AggregateRequest(BaseModel):
    g: Optional[str] = None
    y: Optional[str] = None
    agg: Optional[str] = "sum"
    order: Optional[str] = "desc"
    limit: Optional[int] = 20
    groups: bool = False


class HistogramRequest(BaseModel):
    col: Optional[str] = None
    bins: Optional[int] = 10


class ColumnRequest(BaseModel):
    col: Optional[str] = None


class ScatterRequest(BaseModel):
    x: Optional[str] = None
    y: Optional[str] = None
    limit: Optional[int] = 5000


class DistinctRequest(ColumnRequest):
    limit: Optional[int] = 500


class WelchRequest(BaseModel):
    g: Optional[str] = None
    y: Optional[str] = None
    a: Any = None
    b: Any = None


class RegressionRequest(BaseModel):
    x: Optional[str] = None
    y: Optional[str] = None


class CleanRequest(BaseModel):
    """``op`` plus whatever options that operation takes (strategy, marker, column)."""
    model_config = ConfigDict(extra="allow")
    op: Optional[str] = None


class FormulaRequest(BaseModel):
    name: Optional[str] = None
    expr: Optional[str] = None


class SqlRequest(BaseModel):
    query: Optional[str] = None


class OpenStagedRequest(BaseModel):
    table: Optional[str] = None
    link: bool = False


class ExportRequest(BaseModel):
    kind: Optional[str] = None
    format: Optional[str] = "csv"
    query: Optional[str] = None
    g: Optional[str] = None
    y: Optional[str] = None
    agg: Optional[str] = "sum"


class IdRequest(BaseModel):
    id: Optional[str] = None


class SourceColumnsRequest(IdRequest):
    source: Optional[str] = None


class DeleteStreamRequest(IdRequest):
    drop: bool = False


class RunsRequest(BaseModel):
    limit: Optional[int] = 50
    stream: Optional[str] = None


# --------------------------------------------------------------------------
# responses
# --------------------------------------------------------------------------

def _json(body, status=200):
    """Serialize exactly as the engine always has: anything unknown becomes text."""
    return Response(json.dumps(body, default=str).encode("utf-8"), status_code=status,
                    media_type="application/json; charset=utf-8")


def _error(message, status=400):
    return _json({"error": message}, status)


def _failure(exc):
    """Map an exception from the engine to the response the page expects."""
    if isinstance(exc, (UserError, PipelineError)):
        return _error(str(exc))
    if isinstance(exc, duckdb.Error):
        text = str(exc)
        return _error(text.split("\n")[0] if "LINE" not in text else text)
    if isinstance(exc, (ValueError, TypeError, KeyError, IndexError)):
        return _error("Bad request: %s" % exc)
    sys.stderr.write("Unexpected error: %r\n" % (exc,))
    return _error("Engine error: %s" % exc, 500)


# --------------------------------------------------------------------------
# the app
# --------------------------------------------------------------------------

def create_app(engine, token, port, ui_root=None, log=False):
    """Build the FastAPI app for one engine.

    ``ui_root`` is the folder holding ``index.html``; without it the API still
    works and ``/`` returns a short plain-text note.
    """
    allowed_hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port, "[::1]:%d" % port}
    token_bytes = token.encode("utf-8")
    ui_root = os.path.abspath(ui_root) if ui_root else None

    app = FastAPI(title="ReData engine", version=VERSION, docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json")

    def token_ok(request):
        got = request.headers.get(TOKEN_HEADER) or ""
        if not got and request.url.path.startswith("/api/download/"):
            got = request.query_params.get("t") or ""  # a plain link cannot set a header
        return secrets.compare_digest(got.encode("utf-8"), token_bytes)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        is_api = path.startswith("/api/")
        if (request.headers.get("host") or "") not in allowed_hosts:
            response = _error("Forbidden host.", 403)
        elif (is_api or request.method != "GET") and not token_ok(request):
            response = _error("Missing or wrong engine token.", 403)
        elif path != "/api/stage" and int(request.headers.get("content-length") or 0) > MAX_JSON_BODY:
            response = _error("Request too large.")
        else:
            try:
                response = await call_next(request)
            except Exception as exc:  # a bug in a route must still answer as {"error": ...}
                response = _failure(exc)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        if log and is_api:
            sys.stdout.write("  %s %s %s %d\n" % (time.strftime("%H:%M:%S"), request.method, path, response.status_code))
        return response

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        first = (exc.errors() or [{}])[0]
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        return _error("Bad request: %s" % (": ".join(x for x in (where, first.get("msg", "")) if x) or "invalid body"))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return _error("Not found." if exc.status_code == 404 else str(exc.detail), exc.status_code)

    def run(fn, lock=True):
        """Call the engine, time it, and turn its exceptions into error responses."""
        started = time.time()
        try:
            if lock:
                with engine.lock:
                    result = fn()
            else:
                result = fn()
        except Exception as exc:  # every failure becomes {"error": ...}
            return _failure(exc)
        if isinstance(result, dict):
            result.setdefault("ms", int((time.time() - started) * 1000))
        return _json(result)

    # ---- dataset API ---------------------------------------------------------
    api = APIRouter(prefix="/api", tags=["dataset"])

    @api.get("/status")
    @api.post("/status")
    def status():
        return run(engine.status)

    @api.post("/stage")
    async def stage_upload(request: Request, name: str = "dataset.csv"):
        """Copy an uploaded file into the workspace. The body is the raw file."""
        length = int(request.headers.get("content-length") or 0)
        if length <= 0:
            return _error("The selected file is empty.")
        upload = None
        try:
            upload = engine.begin_upload(name)
            received = 0
            with open(upload["path"], "wb") as fh:
                async for chunk in request.stream():
                    fh.write(chunk)
                    received += len(chunk)
            if received < length:
                raise UserError("The upload was interrupted before the whole file arrived.")
            # the file copy runs outside the lock; DuckDB work takes it inside
            return _json(await run_in_threadpool(engine.finish_upload, upload))
        except ClientDisconnect:
            engine.abort_upload(upload)
            return _error("The upload was interrupted before the whole file arrived.")
        except Exception as exc:
            if upload and upload["id"] not in engine.stages:
                engine.abort_upload(upload)
            return _failure(exc)

    @api.post("/stage_path")
    def stage_path(body: StagePathRequest = Body(default_factory=StagePathRequest)):
        return run(lambda: engine.stage_path(body.path))

    @api.post("/preview")
    def preview(body: PreviewRequest = Body(default_factory=PreviewRequest)):
        return run(lambda: {"preview": engine.excel_preview(body.stage, body.sheet)})

    @api.post("/discard")
    def discard(body: StageRequest = Body(default_factory=StageRequest)):
        def go():
            engine.drop_stage(body.stage)
            return {"ok": True}
        return run(go)

    @api.post("/load")
    def load(body: LoadRequest = Body(default_factory=LoadRequest)):
        return run(lambda: {"meta": engine.load(body.stage, body.header, body.names or None, body.sheet)})

    @api.post("/meta")
    def meta():
        return run(lambda: {"meta": engine.meta()})

    @api.post("/rows")
    def rows(body: RowsRequest = Body(default_factory=RowsRequest)):
        return run(lambda: engine.rows(body.offset, body.limit, body.sort, body.dir, body.column, body.query))

    @api.post("/aggregate")
    def aggregate(body: AggregateRequest = Body(default_factory=AggregateRequest)):
        return run(lambda: engine.aggregate(body.g, body.y, body.agg, body.order, body.limit, body.groups))

    @api.post("/histogram")
    def histogram(body: HistogramRequest = Body(default_factory=HistogramRequest)):
        return run(lambda: engine.histogram(body.col, body.bins))

    @api.post("/box")
    def box(body: ColumnRequest = Body(default_factory=ColumnRequest)):
        return run(lambda: engine.box(body.col))

    @api.post("/scatter")
    def scatter(body: ScatterRequest = Body(default_factory=ScatterRequest)):
        return run(lambda: engine.scatter(body.x, body.y, body.limit))

    @api.post("/distinct")
    def distinct(body: DistinctRequest = Body(default_factory=DistinctRequest)):
        return run(lambda: engine.distinct(body.col, body.limit))

    @api.post("/welch")
    def welch(body: WelchRequest = Body(default_factory=WelchRequest)):
        return run(lambda: engine.welch(body.g, body.y, body.a, body.b))

    @api.post("/regression")
    def regression(body: RegressionRequest = Body(default_factory=RegressionRequest)):
        return run(lambda: engine.regression(body.x, body.y))

    @api.post("/clean")
    def clean(body: CleanRequest = Body(default_factory=CleanRequest)):
        def go():
            message = engine.clean(body.op, **body.model_dump(exclude={"op"}))
            return {"message": message, "meta": engine.meta()}
        return run(go)

    @api.post("/formula")
    def formula(body: FormulaRequest = Body(default_factory=FormulaRequest)):
        def go():
            result = engine.formula(body.name, body.expr)
            result["meta"] = engine.meta()
            return result
        return run(go)

    @api.post("/sql")
    def sql(body: SqlRequest = Body(default_factory=SqlRequest)):
        return run(lambda: engine.sql(body.query))

    @api.post("/open_staged")
    def open_staged(body: OpenStagedRequest = Body(default_factory=OpenStagedRequest)):
        return run(lambda: {"meta": engine.open_staged(body.table, body.link)})

    @api.post("/export")
    def export(body: ExportRequest = Body(default_factory=ExportRequest)):
        return run(lambda: engine.export(body.kind, body.format, body.query, body.g, body.y, body.agg))

    @api.get("/download/{export_id}")
    def download(export_id: str):
        path = engine.exports.get(export_id)
        if not path or not os.path.isfile(path):
            return _error("This export has expired. Export again.", 404)
        name = os.path.basename(path)
        ctype = "application/json" if name.endswith(".json") else "text/csv; charset=utf-8"
        return FileResponse(path, media_type=ctype, filename=name)

    # ---- pipeline API --------------------------------------------------------
    # These do not take the engine lock: the pipeline has its own locks and
    # cursors, so a long sync never blocks the dataset views.
    pipe = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

    def pipeline():
        if engine.pipeline is None:
            raise UserError("The pipeline is not running.")
        return engine.pipeline

    def pipe_run(fn):
        return run(lambda: fn(pipeline()), lock=False)

    @pipe.post("/catalog")
    def catalog():
        return pipe_run(lambda p: {"catalog": p.catalog()})

    @pipe.post("/overview")
    def overview():
        return pipe_run(lambda p: p.overview())

    @pipe.post("/save_connection")
    def save_connection(body: Dict[str, Any] = Body(default_factory=dict)):
        return pipe_run(lambda p: p.save_connection(body))

    @pipe.post("/delete_connection")
    def delete_connection(body: IdRequest = Body(default_factory=IdRequest)):
        return pipe_run(lambda p: p.delete_connection(body.id))

    @pipe.post("/test_connection")
    def test_connection(body: IdRequest = Body(default_factory=IdRequest)):
        return pipe_run(lambda p: p.test_connection(body.id))

    @pipe.post("/snowflake_key")
    def snowflake_key(body: IdRequest = Body(default_factory=IdRequest)):
        return pipe_run(lambda p: p.snowflake_key(body.id))

    @pipe.post("/source_tables")
    def source_tables(body: IdRequest = Body(default_factory=IdRequest)):
        return pipe_run(lambda p: p.source_tables(body.id))

    @pipe.post("/source_columns")
    def source_columns(body: SourceColumnsRequest = Body(default_factory=SourceColumnsRequest)):
        return pipe_run(lambda p: p.source_columns(body.id, body.source))

    @pipe.post("/save_stream")
    def save_stream(body: Dict[str, Any] = Body(default_factory=dict)):
        return pipe_run(lambda p: p.save_stream(body))

    @pipe.post("/delete_stream")
    def delete_stream(body: DeleteStreamRequest = Body(default_factory=DeleteStreamRequest)):
        return pipe_run(lambda p: p.delete_stream(body.id, body.drop))

    @pipe.post("/reset_stream")
    def reset_stream(body: IdRequest = Body(default_factory=IdRequest)):
        return pipe_run(lambda p: p.reset_stream(body.id))

    @pipe.post("/sync_now")
    def sync_now(body: IdRequest = Body(default_factory=IdRequest)):
        return pipe_run(lambda p: p.enqueue(body.id))

    @pipe.post("/runs")
    def runs(body: RunsRequest = Body(default_factory=RunsRequest)):
        return pipe_run(lambda p: {"runs": p.runs(int(body.limit or 50), body.stream)})

    @pipe.post("/{action:path}", include_in_schema=False)
    def unknown_pipeline_action(action: str):
        return _error("Unknown pipeline action.")

    app.include_router(pipe)

    @api.post("/{rest:path}", include_in_schema=False)
    def unknown_endpoint(rest: str):
        return _error("Unknown engine endpoint.")

    @api.get("/{rest:path}", include_in_schema=False)
    def unknown_get(rest: str):
        return _error("Not found.", 404)

    app.include_router(api)

    # ---- the page itself ---------------------------------------------------------
    @app.post("/{path:path}", include_in_schema=False)
    def post_outside_api(path: str):
        return _error("Unknown engine endpoint.")

    @app.get("/{path:path}", include_in_schema=False)
    def static(path: str):
        not_found = Response("Not found", 404, media_type="text/plain; charset=utf-8")
        if ui_root is None:
            if path == "":
                return Response("ReData engine %s is running. The browser page is not installed with it; "
                                "start it with --ui <folder containing index.html>.\n" % VERSION,
                                media_type="text/plain; charset=utf-8")
            return not_found
        rel = path or "index.html"
        parts = rel.split("/")
        if any(p.startswith(".") or p == "" for p in parts) or parts[0] == "engine":
            return not_found
        full = os.path.abspath(os.path.join(ui_root, *parts))
        ext = os.path.splitext(full)[1].lower()
        if not full.startswith(ui_root + os.sep) or ext not in STATIC_TYPES or not os.path.isfile(full):
            return not_found
        try:
            with open(full, "rb") as fh:
                body = fh.read()
        except OSError:  # unreadable is the same as absent to the page
            return not_found
        if rel == "index.html":
            # the page gets the token; nothing else can read it
            inject = ("<script>window.REDATA_ENGINE=%s;</script>"
                      % json.dumps({"token": token, "version": VERSION})).encode("utf-8")
            body = re.sub(rb"<head([^>]*)>", lambda m: m.group(0) + inject, body, count=1)
        return Response(body, media_type=STATIC_TYPES[ext])

    return app


# --------------------------------------------------------------------------
# running it
# --------------------------------------------------------------------------

def _bind(first_port, tries=20):
    """Bind the first free loopback port, so two engines can run side by side."""
    for candidate in range(first_port, first_port + tries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", candidate))
            return sock, candidate
        except OSError:
            sock.close()
    return None, None


def serve(engine, port=8765, ui_root=None, open_browser=True):
    """Serve the engine on the loopback address until Ctrl+C."""
    import uvicorn

    sock, port = _bind(port)
    if sock is None:
        sys.exit("No free port in the 20 ports from the one requested.")
    token = secrets.token_urlsafe(24)
    app = create_app(engine, token, port, ui_root=ui_root, log=True)
    url = "http://127.0.0.1:%d/" % port
    print("")
    print("  ReData local engine %s  (DuckDB %s)" % (VERSION, duckdb.__version__))
    print("  Open:       %s" % url)
    print("  Workspace:  %s" % engine.workspace)
    if ui_root is None:
        print("  Page:       not found; serving the API only")
    if engine.state.get("name"):
        print("  Dataset:    %s (restored from last session)" % engine.state["name"])
    if engine.pipeline and engine.pipeline.cfg["streams"]:
        n = len(engine.pipeline.cfg["streams"])
        print("  Syncs:      %d configured; scheduled ones run while this window is open" % n)
    print("  Stop:       press Ctrl+C in this window")
    print("", flush=True)
    if open_browser and ui_root is not None:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    config = uvicorn.Config(app, log_level="warning", access_log=False, server_header=False,
                            timeout_graceful_shutdown=3)
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        print("\n  Stopping ReData engine…")
        sock.close()
        engine.close()
