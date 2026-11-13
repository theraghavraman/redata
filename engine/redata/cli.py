"""Command line for the ReData engine.

    redata serve                      the engine and the browser page
    redata connectors                 connector types and their settings
    redata connection add|list|test|remove
    redata stream add|list|reset|remove
    redata sync orders                run one sync now and wait for it
    redata sync --all                 run every sync, e.g. from cron
    redata runs                       sync history
    redata tables                     staging tables
    redata sql "SELECT ..."           read-only query

Everything except ``serve`` works without a browser. All commands share one
workspace (``--workspace`` or ``REDATA_WORKSPACE``), which holds the DuckDB
database, the connection settings and the saved sync state. DuckDB allows one
process per database file, so stop ``redata serve`` before running a command
against the same workspace.
"""

import argparse
import csv
import json
import os
import sys

from . import __version__ as VERSION

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(PACKAGE_DIR)
CHECKOUT_ROOT = os.path.dirname(ENGINE_DIR)


def find_ui():
    """The folder with index.html when running from a source checkout, else None."""
    return CHECKOUT_ROOT if os.path.isfile(os.path.join(CHECKOUT_ROOT, "index.html")) else None


def default_workspace():
    env = os.environ.get("REDATA_WORKSPACE")
    if env:
        return env
    if find_ui():  # source checkout: the folder the launch scripts have always used
        return os.path.join(ENGINE_DIR, "workspace")
    return os.path.join(os.path.expanduser("~"), ".redata", "workspace")


class CliError(Exception):
    """A problem to report on stderr with exit code 1."""


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def open_engine(args, pipeline=True, background=False):
    import duckdb
    from .engine import Engine

    workspace = os.path.abspath(args.workspace or default_workspace())
    try:
        engine = Engine(workspace, getattr(args, "memory_limit", None), getattr(args, "threads", None))
    except duckdb.IOException as exc:
        raise CliError("The workspace %s is in use by another engine. Stop it (or pass a different "
                       "--workspace) and try again.\n  %s" % (workspace, str(exc).split("\n")[0]))
    if pipeline:
        engine.start_pipeline(background=background)
    return engine


def print_table(headers, rows, out=None):
    out = out or sys.stdout
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = "  ".join("%-" + str(w) + "s" for w in widths)
    out.write((line % tuple(headers)).rstrip() + "\n")
    out.write("  ".join("-" * w for w in widths) + "\n")
    for r in cells:
        out.write((line % tuple(r)).rstrip() + "\n")


def find_connection(pipe, ref):
    hits = [c for c in pipe.cfg["connections"] if ref in (c["id"], c["name"])]
    if not hits:
        hits = [c for c in pipe.cfg["connections"] if c["name"].lower() == str(ref).lower()]
    if not hits:
        raise CliError("No connection called %s. See: redata connection list" % ref)
    return hits[0]


def find_stream(pipe, ref):
    hits = [s for s in pipe.cfg["streams"] if ref in (s["id"], s["target"])]
    if not hits:
        raise CliError("No sync called %s. See: redata stream list" % ref)
    return hits[0]


def parse_settings(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise CliError("Settings are written KEY=VALUE, got: %s" % pair)
        key, value = pair.split("=", 1)
        out[key.strip()] = value
    return out


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_serve(args):
    from .server import serve

    ui = os.path.abspath(args.ui) if args.ui else find_ui()
    if args.ui and not os.path.isfile(os.path.join(ui, "index.html")):
        raise CliError("No index.html in %s." % ui)
    engine = open_engine(args, background=True)
    serve(engine, port=args.port, ui_root=ui, open_browser=not args.no_browser)
    return 0


def cmd_connectors(args):
    from . import connectors as C

    if args.type:
        spec = C.CATALOG.get(args.type)
        if not spec:
            raise CliError("Unknown connector type %s. See: redata connectors" % args.type)
        print("%s (%s)\n%s\n" % (spec["label"], args.type, spec["note"]))
        print_table(["setting", "required", "secret", "default", "meaning"],
                    [[f["key"], "yes" if f["required"] else "", "yes" if f["secret"] else "",
                      f.get("default", ""), f["label"]] for f in spec["fields"]])
        return 0
    print_table(["type", "group", "name"], [[k, v["group"], v["label"]] for k, v in C.CATALOG.items()])
    return 0


def cmd_connection(args):
    from .pipeline import PipelineError

    engine = open_engine(args)
    pipe = engine.pipeline
    try:
        if args.action == "list":
            ov = pipe.overview()
            print_table(["name", "type", "id", "last test"],
                        [[c["name"], c["type"], c["id"],
                          ("ok" if c["lastTest"]["ok"] else "failed: " + c["lastTest"]["message"]) if c.get("lastTest") else ""]
                         for c in ov["connections"]])
        elif args.action == "add":
            body = {"type": args.type, "name": args.name, "values": parse_settings(args.set)}
            if args.name and any(c["name"].lower() == args.name.lower() for c in pipe.cfg["connections"]):
                body["id"] = find_connection(pipe, args.name)["id"]  # same name: update it
            cid = pipe.save_connection(body)["id"]
            print("Saved connection %s (%s)." % (pipe._conn(cid)["name"], cid))
        elif args.action == "test":
            result = pipe.test_connection(find_connection(pipe, args.name)["id"])
            print(result["message"])
            return 0 if result["ok"] else 1
        elif args.action == "remove":
            pipe.delete_connection(find_connection(pipe, args.name)["id"])
            print("Removed connection %s." % args.name)
        return 0
    except PipelineError as exc:
        raise CliError(str(exc))
    finally:
        engine.close()


def cmd_stream(args):
    from .pipeline import PipelineError

    engine = open_engine(args)
    pipe = engine.pipeline
    try:
        if args.action == "list":
            ov = pipe.overview()
            print_table(["target", "connection", "source", "mode", "cursor", "saved cursor", "every (min)", "last run", "id"],
                        [[s["target"], s["connectionName"], s["source"], s["mode"], s.get("cursor"),
                          s["cursorDisplay"], s.get("interval") or "", s["state"].get("last_status"), s["id"]]
                         for s in ov["streams"]])
        elif args.action == "add":
            body = {"connection_id": find_connection(pipe, args.connection)["id"], "source": args.source,
                    "mode": args.mode, "cursor": args.cursor, "keys": args.keys, "target": args.target,
                    "interval": args.interval}
            if args.target and any(s["target"] == args.target for s in pipe.cfg["streams"]):
                body["id"] = find_stream(pipe, args.target)["id"]  # same target: update it
            saved = pipe.save_stream(body)
            print("Saved sync staging.%s (%s)." % (saved["target"], saved["id"]))
        elif args.action == "reset":
            pipe.reset_stream(find_stream(pipe, args.name)["id"])
            print("Cleared the saved state of %s; the next sync reads everything again." % args.name)
        elif args.action == "remove":
            pipe.delete_stream(find_stream(pipe, args.name)["id"], drop_table=args.drop_table)
            print("Removed sync %s." % args.name)
        return 0
    except PipelineError as exc:
        raise CliError(str(exc))
    finally:
        engine.close()


def cmd_sync(args):
    engine = open_engine(args)
    pipe = engine.pipeline
    try:
        if args.all:
            streams = [s for s in pipe.cfg["streams"] if s.get("enabled", True)]
        else:
            streams = [find_stream(pipe, ref) for ref in args.streams]
        if not streams:
            raise CliError("Nothing to sync. Name a sync, or use --all. See: redata stream list")
        results, failed = [], 0
        for s in streams:
            status = pipe.run(s["id"], "cli")
            run = pipe.runs(1, s["id"])[0]
            failed += status != "success"
            results.append(run)
            if not args.json:
                print("%-8s staging.%s  read %s  written %s  rows now %s  cursor %s -> %s  %s" % (
                    status, s["target"], run["rows_read"], run["rows_written"], run["table_rows"],
                    run["cursor_from"], run["cursor_to"], run["message"] or ""))
        if args.json:
            json.dump(results, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        return 1 if failed else 0
    finally:
        engine.close()


def cmd_runs(args):
    engine = open_engine(args)
    try:
        sid = find_stream(engine.pipeline, args.stream)["id"] if args.stream else None
        runs = engine.pipeline.runs(args.limit, sid)
        if args.json:
            json.dump(runs, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        else:
            print_table(["started", "sync", "mode", "trigger", "status", "read", "written", "rows", "cursor to", "message"],
                        [[r["started_at"][:19], r["stream"], r["mode"], r["trigger"], r["status"], r["rows_read"],
                          r["rows_written"], r["table_rows"], r["cursor_to"], r["message"]] for r in runs])
        return 0
    finally:
        engine.close()


def cmd_tables(args):
    engine = open_engine(args)
    try:
        print_table(["table", "rows", "columns"],
                    [["staging." + t["table"], t["rows"], t["columns"]] for t in engine.pipeline.staged_tables()])
        return 0
    finally:
        engine.close()


def cmd_sql(args):
    from .util import UserError

    engine = open_engine(args, pipeline=False)
    try:
        try:
            result = engine.sql(args.query)
        except UserError as exc:
            raise CliError(str(exc))
        cols, rows = result["columns"], result["rows"]
        if args.format == "json":
            json.dump(rows, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.format == "csv":
            writer = csv.writer(sys.stdout)
            writer.writerow(cols)
            writer.writerows([[r[c] for c in cols] for r in rows])
        else:
            print_table(cols, [[r[c] for c in cols] for r in rows])
        if result["truncated"]:
            sys.stderr.write("Only the first %d rows are shown.\n" % len(rows))
        return 0
    finally:
        engine.close()


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default=None,
                        help="folder for the database, settings and sync state "
                             "(default: $REDATA_WORKSPACE, else engine/workspace in a checkout, else ~/.redata/workspace)")
    common.add_argument("--memory-limit", default=None, help="DuckDB memory limit, e.g. 4GB (default: 80%% of RAM)")
    common.add_argument("--threads", type=int, default=None, help="DuckDB worker threads (default: all cores)")

    ap = argparse.ArgumentParser(prog="redata", description="ReData engine: sync sources into DuckDB staging tables.")
    ap.add_argument("--version", action="version", version="redata " + VERSION)
    sub = ap.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("serve", parents=[common], help="run the engine and the browser page")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    p.add_argument("--ui", default=None, help="folder containing index.html (default: the source checkout)")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("connectors", parents=[common], help="list connector types, or the settings of one")
    p.add_argument("type", nargs="?")
    p.set_defaults(fn=cmd_connectors)

    p = sub.add_parser("connection", help="add, list, test or remove connections")
    actions = p.add_subparsers(dest="action", metavar="action", required=True)
    actions.add_parser("list", parents=[common])
    a = actions.add_parser("add", parents=[common], help="add a connection, or update the one with this name")
    a.add_argument("--type", required=True, help="connector type; see: redata connectors")
    a.add_argument("--name", required=True)
    a.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="a setting; repeat for each. Write a secret as env:NAME to read it from the environment")
    for name in ("test", "remove"):
        a = actions.add_parser(name, parents=[common])
        a.add_argument("name")
    p.set_defaults(fn=cmd_connection)

    p = sub.add_parser("stream", help="add, list, reset or remove syncs")
    actions = p.add_subparsers(dest="action", metavar="action", required=True)
    actions.add_parser("list", parents=[common])
    a = actions.add_parser("add", parents=[common], help="add a sync, or update the one with this target")
    a.add_argument("--connection", required=True)
    a.add_argument("--source", required=True, help="table, view, SELECT, file pattern or API path")
    a.add_argument("--mode", choices=["full", "append", "upsert"], default="full")
    a.add_argument("--cursor", default=None, help="increasing column for append and upsert, e.g. updated_at")
    a.add_argument("--keys", default=None, help="key column(s) for upsert, comma separated")
    a.add_argument("--target", default=None, help="staging table name (default: from the connection and source)")
    a.add_argument("--interval", type=int, default=0, help="minutes between scheduled runs under 'redata serve'")
    a = actions.add_parser("reset", parents=[common], help="forget the saved cursor and file list")
    a.add_argument("name")
    a = actions.add_parser("remove", parents=[common])
    a.add_argument("name")
    a.add_argument("--drop-table", action="store_true", help="also drop the staging table")
    p.set_defaults(fn=cmd_stream)

    p = sub.add_parser("sync", parents=[common], help="run syncs now and wait for them")
    p.add_argument("streams", nargs="*", help="staging table names or sync ids")
    p.add_argument("--all", action="store_true", help="every enabled sync")
    p.add_argument("--json", action="store_true", help="print the run records as JSON")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("runs", parents=[common], help="sync history")
    p.add_argument("--stream", default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_runs)

    p = sub.add_parser("tables", parents=[common], help="staging tables and their sizes")
    p.set_defaults(fn=cmd_tables)

    p = sub.add_parser("sql", parents=[common], help="run a read-only query, e.g. against staging.orders")
    p.add_argument("query")
    p.add_argument("--format", choices=["table", "csv", "json"], default="table")
    p.set_defaults(fn=cmd_sql)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    if not hasattr(args, "workspace"):
        args.workspace = None
    try:
        return args.fn(args) or 0
    except CliError as exc:
        sys.stderr.write("redata: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
