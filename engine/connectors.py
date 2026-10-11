"""Source connectors for the ReData engine.

Every connector reads from one kind of source and hands rows to the pipeline
either as Arrow tables (databases, APIs) or as a DuckDB-readable file list
(files, data lakes). Drivers are imported lazily, so the engine still starts
when an optional driver is missing; the error then says what to install.

Database connectors use the vendor's Python driver instead of DuckDB's
scanner extensions so they work on networks that block extension downloads.
"""

import datetime
import decimal
import fnmatch
import glob
import json
import os
import re
import urllib.parse
import urllib.request
import uuid

BATCH_ROWS = 50_000


class SourceError(Exception):
    """Problem talking to a source; the message is shown in the UI."""


def _need(module, pip_name):
    import importlib
    try:
        return importlib.import_module(module)
    except ImportError:
        raise SourceError(
            "The %s driver is not installed. Run start-engine again (it installs it), "
            "or: python -m pip install %s" % (module, pip_name))


# --------------------------------------------------------------------------
# connector catalogue: drives the "New connection" form in the UI
# --------------------------------------------------------------------------

def field(key, label, kind="text", required=True, secret=False, placeholder="", help="", options=None, default=None):
    f = {"key": key, "label": label, "kind": kind, "required": required, "secret": secret,
         "placeholder": placeholder, "help": help}
    if options:
        f["options"] = options
    if default is not None:
        f["default"] = default
    return f


CATALOG = {
    "postgres": {
        "label": "PostgreSQL", "group": "Database",
        "note": "Works with Postgres, Neon, Supabase, Aiven, AWS RDS / Aurora, Azure and Google Cloud SQL.",
        "fields": [
            field("host", "Host", placeholder="ep-xyz.ap-southeast-1.aws.neon.tech"),
            field("port", "Port", "number", default="5432"),
            field("database", "Database", placeholder="neondb"),
            field("user", "User"),
            field("password", "Password", "password", secret=True),
            field("sslmode", "SSL mode", "select", required=False, options=["prefer", "require", "disable", "verify-full"], default="prefer"),
        ],
    },
    "mysql": {
        "label": "MySQL / MariaDB", "group": "Database",
        "note": "Works with MySQL, MariaDB, Aiven, AWS RDS, Azure Database for MySQL and Oracle MySQL HeatWave.",
        "fields": [
            field("host", "Host"),
            field("port", "Port", "number", default="3306"),
            field("database", "Database"),
            field("user", "User"),
            field("password", "Password", "password", secret=True),
            field("ssl", "Use SSL", "select", required=False, options=["auto", "required", "off"], default="auto"),
        ],
    },
    "sqlserver": {
        "label": "SQL Server / Azure SQL", "group": "Database",
        "note": "Works with SQL Server 2012+, Azure SQL Database (including the free offer) and Azure SQL Managed Instance.",
        "fields": [
            field("host", "Server", placeholder="myserver.database.windows.net"),
            field("port", "Port", "number", default="1433"),
            field("database", "Database"),
            field("user", "User"),
            field("password", "Password", "password", secret=True),
        ],
    },
    "snowflake": {
        "label": "Snowflake", "group": "Warehouse",
        "note": "Key pair is the recommended sign-in: Snowflake is ending password-only sign-ins. Choose it, select Generate key, and run the SQL it shows in a Snowflake worksheet.",
        "fields": [
            field("account", "Account identifier", placeholder="ORGNAME-ACCOUNTNAME", help="Shown under your name > Account > View account details."),
            field("user", "User"),
            field("auth", "Sign-in method", "select", options=["keypair", "externalbrowser", "password"], default="keypair",
                  help="keypair: generated here. externalbrowser: signs in through your browser (SSO / MFA). password: also accepts a programmatic access token."),
            field("password", "Password or access token", "password", required=False, secret=True),
            field("private_key_passphrase", "Private key passphrase", "password", required=False, secret=True,
                  help="Only if you use your own encrypted key file."),
            field("private_key_path", "Private key file", required=False, help="Filled in when you select Generate key."),
            field("warehouse", "Warehouse", default="COMPUTE_WH"),
            field("database", "Database"),
            field("schema", "Schema", required=False, default="PUBLIC"),
            field("role", "Role", required=False),
        ],
    },
    "sqlite": {
        "label": "SQLite file", "group": "Database",
        "note": "A .db / .sqlite file on this computer.",
        "fields": [field("path", "File path", placeholder="C:\\data\\shop.db")],
    },
    "files": {
        "label": "Folder of files", "group": "Files and lakes",
        "note": "CSV, TSV, JSON, NDJSON, Parquet and Excel files in a folder on this computer or a network drive. Incremental mode picks up only new or changed files.",
        "fields": [field("folder", "Folder path", placeholder="D:\\exports\\daily")],
    },
    "s3": {
        "label": "Amazon S3 / S3-compatible", "group": "Files and lakes",
        "note": "A bucket and prefix. Works with AWS S3, Cloudflare R2, MinIO and other S3-compatible stores (set the endpoint). Incremental mode downloads only new objects.",
        "fields": [
            field("bucket", "Bucket"),
            field("region", "Region", required=False, default="ap-south-1"),
            field("access_key_id", "Access key ID", required=False),
            field("secret_access_key", "Secret access key", "password", required=False, secret=True),
            field("endpoint_url", "Endpoint URL", required=False, help="Only for S3-compatible stores such as R2 or MinIO."),
        ],
    },
    "http": {
        "label": "File at a URL", "group": "Files and lakes",
        "note": "A CSV, JSON or Parquet file published at an http(s) address, downloaded again on every sync.",
        "fields": [
            field("base_url", "Base URL", required=False, placeholder="https://example.com/exports/"),
            field("headers", "Request headers (JSON)", "textarea", required=False, secret=True, placeholder='{"Authorization": "Bearer ..."}'),
        ],
    },
    "rest": {
        "label": "REST API (JSON)", "group": "Applications",
        "note": "Any JSON API that returns a list of records. Supports bearer tokens, a records path, next-page links and an incremental 'since' parameter.",
        "fields": [
            field("base_url", "Base URL", placeholder="https://api.example.com/v1/"),
            field("headers", "Request headers (JSON)", "textarea", required=False, secret=True, placeholder='{"Authorization": "Bearer ..."}'),
            field("records_path", "Records path", required=False, placeholder="data.items", help="Where the list of records sits in the response. Empty if the response is the list."),
            field("next_path", "Next page link path", required=False, placeholder="links.next", help="Field holding the URL of the next page, if the API pages its results."),
            field("since_param", "Incremental parameter", required=False, placeholder="updated_since", help="Query parameter that receives the last cursor value."),
        ],
    },
}


def catalog():
    return CATALOG


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _rows_to_arrow(names, rows):
    pa = _need("pyarrow", "pyarrow")
    cols = list(zip(*rows)) if rows else [[] for _ in names]
    arrays = []
    for col in cols:
        col = list(col)
        sample = next((v for v in col if v is not None), None)
        if isinstance(sample, (dict, list, tuple)):
            col = [None if v is None else json.dumps(v, default=str) for v in col]
        elif isinstance(sample, uuid.UUID) or (sample is not None and type(sample).__name__ in ("UUID", "IPv4Address", "IPv6Address", "Range")):
            col = [None if v is None else str(v) for v in col]
        try:
            arr = pa.array(col)
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
            arr = pa.array([None if v is None else str(v) for v in col])
        if pa.types.is_null(arr.type):
            arr = pa.array(col, type=pa.string())
        arrays.append(arr)
    return pa.Table.from_arrays(arrays, names=unique_names(names))


def unique_names(names):
    seen, out = set(), []
    for i, n in enumerate(names):
        h = str(n or "").strip() or "column_%d" % (i + 1)
        base, k = h, 2
        while h.lower() in seen:
            h = "%s_%d" % (base, k)
            k += 1
        seen.add(h.lower())
        out.append(h)
    return out


def _dig(obj, path):
    if not path:
        return obj
    for part in str(path).split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            obj = obj.get(part)
    return obj


def _headers(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        h = json.loads(raw)
    except ValueError:
        raise SourceError("Request headers must be JSON, for example {\"Authorization\": \"Bearer ...\"}.")
    if not isinstance(h, dict):
        raise SourceError("Request headers must be a JSON object.")
    return {str(k): str(v) for k, v in h.items()}


def _http_get(url, headers, timeout=120):
    req = urllib.request.Request(url, headers=dict({"User-Agent": "ReData-engine"}, **headers))
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise SourceError("%s returned HTTP %s %s" % (url, e.code, e.reason))
    except urllib.error.URLError as e:
        raise SourceError("Could not reach %s: %s" % (url, e.reason))


FILE_EXTS = ("csv", "tsv", "txt", "json", "ndjson", "jsonl", "parquet", "xlsx", "xlsm", "xls")


def file_kind(name):
    ext = os.path.splitext(name.lower())[1].lstrip(".")
    if ext in ("csv", "tsv", "txt"):
        return "csv"
    if ext in ("json", "ndjson", "jsonl"):
        return "json"
    if ext == "parquet":
        return "parquet"
    if ext in ("xlsx", "xlsm", "xls"):
        return "excel"
    return None


# --------------------------------------------------------------------------
# database sources (DB-API drivers)
# --------------------------------------------------------------------------

class DbSource:
    placeholder = "%s"
    kind = "db"

    def __init__(self, params, secrets, workspace):
        self.p = params
        self.s = secrets
        self.workspace = workspace

    # dialect hooks
    def q(self, name):
        return '"' + str(name).replace('"', '""') + '"'

    def qualified(self, table):
        parts = [x for x in str(table).split(".") if x != ""] if not str(table).startswith('"') else [str(table)]
        return ".".join(self.q(x) for x in parts)

    def connect(self):
        raise NotImplementedError

    def list_sql(self):
        raise NotImplementedError

    # common behaviour
    def test(self):
        con = self.connect()
        try:
            cur = con.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
        finally:
            con.close()
        return "Connected."

    def list_tables(self):
        con = self.connect()
        try:
            cur = con.cursor()
            cur.execute(self.list_sql())
            return ["%s.%s" % (r[0], r[1]) if r[0] else str(r[1]) for r in cur.fetchall()]
        finally:
            con.close()

    def base_query(self, source):
        if str(source).lstrip().lower().startswith(("select ", "with ", "select\n", "with\n")):
            return "(%s) redata_src" % source.strip().rstrip(";")
        return self.qualified(source)

    def columns(self, source):
        con = self.connect()
        try:
            cur = con.cursor()
            cur.execute(self.limit_zero(self.base_query(source)))
            cols = [d[0] for d in cur.description]
            cur.fetchall()
            return cols
        finally:
            con.close()

    def limit_zero(self, frm):
        return "SELECT * FROM %s WHERE 1=0" % frm

    def read(self, source, cursor_col=None, cursor_value=None, inclusive=False):
        """Yield Arrow tables of up to BATCH_ROWS rows."""
        frm = self.base_query(source)
        sql = "SELECT * FROM %s" % frm
        params = []
        if cursor_col and cursor_value is not None:
            sql += " WHERE %s %s %s" % (self.q(cursor_col), ">=" if inclusive else ">", self.placeholder)
            params.append(cursor_value)
        con = self.connect()
        try:
            cur = self.stream_cursor(con)
            cur.execute(sql, params) if params else cur.execute(sql)
            names = [d[0] for d in cur.description]
            while True:
                rows = cur.fetchmany(BATCH_ROWS)
                if not rows:
                    break
                yield _rows_to_arrow(names, rows)
        finally:
            con.close()

    def stream_cursor(self, con):
        return con.cursor()


class PostgresSource(DbSource):
    def connect(self):
        psycopg = _need("psycopg", "psycopg[binary]")
        try:
            return psycopg.connect(
                host=self.p.get("host"), port=int(self.p.get("port") or 5432), dbname=self.p.get("database"),
                user=self.p.get("user"), password=self.s.get("password") or None,
                sslmode=self.p.get("sslmode") or "prefer", connect_timeout=15, autocommit=False)
        except psycopg.Error as e:
            raise SourceError(str(e).strip().split("\n")[0])

    def stream_cursor(self, con):
        # a named (server-side) cursor streams large tables instead of loading them all
        return con.cursor(name="redata_%s" % uuid.uuid4().hex[:8])

    def list_sql(self):
        return ("SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1, 2")


class MySqlSource(DbSource):
    def q(self, name):
        return "`" + str(name).replace("`", "``") + "`"

    def connect(self):
        pymysql = _need("pymysql", "pymysql")
        ssl_mode = self.p.get("ssl") or "auto"
        kw = {}
        if ssl_mode == "required":
            kw["ssl"] = {"ssl": {}}
        try:
            return pymysql.connect(
                host=self.p.get("host"), port=int(self.p.get("port") or 3306), database=self.p.get("database"),
                user=self.p.get("user"), password=self.s.get("password") or "", connect_timeout=15,
                charset="utf8mb4", **kw)
        except pymysql.MySQLError as e:
            raise SourceError(str(e))

    def stream_cursor(self, con):
        import pymysql.cursors
        return con.cursor(pymysql.cursors.SSCursor)

    def list_sql(self):
        return ("SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() ORDER BY 2")


class SqlServerSource(DbSource):
    def q(self, name):
        return "[" + str(name).replace("]", "]]") + "]"

    def connect(self):
        pymssql = _need("pymssql", "pymssql")
        try:
            return pymssql.connect(
                server=self.p.get("host"), port=str(self.p.get("port") or 1433), database=self.p.get("database"),
                user=self.p.get("user"), password=self.s.get("password") or "", login_timeout=15, timeout=0,
                tds_version="7.4")
        except pymssql.Error as e:
            raise SourceError(str(e))

    def limit_zero(self, frm):
        return "SELECT TOP 0 * FROM %s" % frm

    def list_sql(self):
        return ("SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type IN ('BASE TABLE','VIEW') ORDER BY 1, 2")


class SqliteSource(DbSource):
    placeholder = "?"

    def connect(self):
        import sqlite3
        path = os.path.expanduser(str(self.p.get("path") or "").strip().strip('"'))
        if not os.path.isfile(path):
            raise SourceError("No SQLite file at " + path)
        return sqlite3.connect("file:%s?mode=ro" % urllib.parse.quote(os.path.abspath(path)), uri=True)

    def list_sql(self):
        return "SELECT '' , name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY 2"


class SnowflakeSource(DbSource):
    def connect(self):
        sf = _need("snowflake.connector", "snowflake-connector-python")
        auth = self.p.get("auth") or "keypair"
        kw = dict(account=self.p.get("account"), user=self.p.get("user"), warehouse=self.p.get("warehouse") or None,
                  database=self.p.get("database") or None, schema=self.p.get("schema") or None,
                  role=self.p.get("role") or None, login_timeout=30, application="ReData")
        if auth == "keypair":
            path = self.p.get("private_key_path")
            if not path or not os.path.isfile(path):
                raise SourceError("No private key yet: select Generate key, run the SQL it shows in Snowflake, then test again.")
            kw["private_key_file"] = path
            if self.s.get("private_key_passphrase"):
                kw["private_key_file_pwd"] = self.s.get("private_key_passphrase")
        elif auth == "externalbrowser":
            kw["authenticator"] = "externalbrowser"
            kw["client_store_temporary_credential"] = True
        else:
            kw["password"] = self.s.get("password") or ""
        try:
            return sf.connect(**{k: v for k, v in kw.items() if v is not None})
        except Exception as e:  # snowflake raises its own error classes
            raise SourceError(str(e).split("\n")[0])

    def list_sql(self):
        db = self.p.get("database")
        prefix = (self.q(db) + ".") if db else ""
        return ("SELECT table_schema, table_name FROM %sinformation_schema.tables "
                "WHERE table_schema <> 'INFORMATION_SCHEMA' ORDER BY 1, 2" % prefix)

    def read(self, source, cursor_col=None, cursor_value=None, inclusive=False):
        frm = self.base_query(source)
        sql = "SELECT * FROM %s" % frm
        params = None
        if cursor_col and cursor_value is not None:
            sql += " WHERE %s %s %%s" % (self.q(cursor_col), ">=" if inclusive else ">")
            params = (cursor_value,)
        con = self.connect()
        try:
            cur = con.cursor()
            cur.execute(sql, params)
            try:
                batches = cur.fetch_arrow_batches()
            except Exception:
                batches = None
            if batches is None:
                names = [d[0] for d in cur.description]
                while True:
                    rows = cur.fetchmany(BATCH_ROWS)
                    if not rows:
                        break
                    yield _rows_to_arrow(names, rows)
            else:
                for b in batches:
                    yield b
        finally:
            con.close()


def snowflake_keypair(workspace, conn_id, user):
    """Create an RSA key pair; return (private key path, ALTER USER statement)."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        raise SourceError("Key generation needs the cryptography package (installed with the Snowflake driver).")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    folder = os.path.join(workspace, "keys")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%s_rsa_key.p8" % conn_id)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    body = "".join(line for line in pub.decode().splitlines() if "-----" not in line)
    user_ident = '"%s"' % str(user or "YOUR_USER").replace('"', '""').upper()
    return path, "ALTER USER %s SET RSA_PUBLIC_KEY='%s';" % (user_ident, body)


# --------------------------------------------------------------------------
# file-like sources: produce local files for DuckDB to read
# --------------------------------------------------------------------------

class FileSource:
    kind = "files"

    def __init__(self, params, secrets, workspace):
        self.p = params
        self.s = secrets
        self.workspace = workspace

    def folder(self):
        f = os.path.abspath(os.path.expanduser(str(self.p.get("folder") or "").strip().strip('"')))
        if not os.path.isdir(f):
            raise SourceError("No folder at " + f)
        return f

    def test(self):
        f = self.folder()
        n = len(self._all(f, "*"))
        return "Folder found: %d data file%s." % (n, "" if n == 1 else "s")

    def _all(self, folder, pattern):
        pat = pattern or "*"
        hits = glob.glob(os.path.join(folder, pat), recursive=True)
        return sorted(p for p in hits if os.path.isfile(p) and file_kind(p))

    def list_tables(self):
        f = self.folder()
        files = [os.path.relpath(p, f) for p in self._all(f, "**/*")]
        exts = sorted({"*." + p.rsplit(".", 1)[-1].lower() for p in files})
        return exts + files[:500]

    def files(self, source, done):
        """Return [(key, local_path)] for files not in `done` (a dict key -> signature)."""
        f = self.folder()
        out = []
        for p in self._all(f, source):
            st = os.stat(p)
            sig = "%d-%d" % (st.st_size, int(st.st_mtime))
            key = os.path.relpath(p, f)
            if done is None or done.get(key) != sig:
                out.append((key, p, sig))
        return out


class S3Source(FileSource):
    def client(self):
        boto3 = _need("boto3", "boto3")
        kw = {"region_name": self.p.get("region") or None}
        if self.p.get("access_key_id"):
            kw["aws_access_key_id"] = self.p.get("access_key_id")
            kw["aws_secret_access_key"] = self.s.get("secret_access_key")
        if self.p.get("endpoint_url"):
            kw["endpoint_url"] = self.p.get("endpoint_url")
        return boto3.client("s3", **{k: v for k, v in kw.items() if v})

    def _objects(self, prefix=""):
        c = self.client()
        token, out = None, []
        try:
            while True:
                kw = {"Bucket": self.p.get("bucket"), "Prefix": prefix or ""}
                if token:
                    kw["ContinuationToken"] = token
                r = c.list_objects_v2(**kw)
                out.extend(r.get("Contents", []))
                if not r.get("IsTruncated"):
                    break
                token = r.get("NextContinuationToken")
        except Exception as e:
            raise SourceError(str(e).split("\n")[0])
        return [o for o in out if file_kind(o["Key"])]

    def test(self):
        n = len(self._objects())
        return "Bucket reachable: %d data object%s." % (n, "" if n == 1 else "s")

    def list_tables(self):
        objs = [o["Key"] for o in self._objects()]
        prefixes = sorted({k.rsplit("/", 1)[0] + "/*." + k.rsplit(".", 1)[-1].lower() for k in objs if "/" in k})
        return prefixes + objs[:500]

    def files(self, source, done):
        pattern = source or "*"
        prefix = pattern.split("*", 1)[0].split("?", 1)[0]
        dest = os.path.join(self.workspace, "downloads", uuid.uuid4().hex)
        out = []
        c = None
        for o in self._objects(prefix):
            key = o["Key"]
            if not fnmatch.fnmatch(key, pattern):
                continue
            sig = "%s-%s" % (o.get("ETag", "").strip('"'), o.get("Size"))
            if done is not None and done.get(key) == sig:
                continue
            c = c or self.client()
            os.makedirs(dest, exist_ok=True)
            local = os.path.join(dest, key.replace("/", "__"))
            try:
                c.download_file(self.p.get("bucket"), key, local)
            except Exception as e:
                raise SourceError("Download of %s failed: %s" % (key, e))
            out.append((key, local, sig))
        return out


class HttpFileSource(FileSource):
    def test(self):
        return "Saved. The address is checked on the first sync."

    def list_tables(self):
        return []

    def files(self, source, done):
        url = urllib.parse.urljoin(self.p.get("base_url") or "", source or "")
        if not url.lower().startswith(("http://", "https://")):
            raise SourceError("Enter an http(s) address.")
        name = os.path.basename(urllib.parse.urlparse(url).path) or "download.csv"
        if not file_kind(name):
            name += ".csv"
        dest = os.path.join(self.workspace, "downloads", uuid.uuid4().hex)
        os.makedirs(dest, exist_ok=True)
        local = os.path.join(dest, name)
        with _http_get(url, _headers(self.s.get("headers"))) as r, open(local, "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        return [(url, local, "always")]


class RestSource:
    kind = "rest"

    def __init__(self, params, secrets, workspace):
        self.p = params
        self.s = secrets
        self.workspace = workspace

    def test(self):
        return "Saved. The API is called on the first sync."

    def list_tables(self):
        return []

    def columns(self, source):
        return []

    def read(self, source, cursor_col=None, cursor_value=None, inclusive=False):
        pa = _need("pyarrow", "pyarrow")
        url = urllib.parse.urljoin(self.p.get("base_url") or "", source or "")
        since = self.p.get("since_param")
        if since and cursor_value is not None:
            v = cursor_value.isoformat() if hasattr(cursor_value, "isoformat") else str(cursor_value)
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({since: v})
        headers = _headers(self.s.get("headers"))
        pages = 0
        while url and pages < 10000:
            with _http_get(url, headers) as r:
                try:
                    body = json.loads(r.read().decode("utf-8"))
                except ValueError:
                    raise SourceError("%s did not return JSON." % url)
            records = _dig(body, self.p.get("records_path"))
            if isinstance(records, dict):
                records = [records]
            if not isinstance(records, list):
                raise SourceError("No list of records at '%s' in the response." % (self.p.get("records_path") or "(top level)"))
            records = [r if isinstance(r, dict) else {"value": r} for r in records]
            if records:
                flat = [{k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in rec.items()} for rec in records]
                names = []
                for rec in flat:
                    for k in rec:
                        if k not in names:
                            names.append(k)
                yield _rows_to_arrow(names, [tuple(rec.get(k) for k in names) for rec in flat])
            nxt = _dig(body, self.p.get("next_path")) if self.p.get("next_path") else None
            url = urllib.parse.urljoin(url, nxt) if isinstance(nxt, str) and nxt else None
            pages += 1


SOURCES = {
    "postgres": PostgresSource,
    "mysql": MySqlSource,
    "sqlserver": SqlServerSource,
    "snowflake": SnowflakeSource,
    "sqlite": SqliteSource,
    "files": FileSource,
    "s3": S3Source,
    "http": HttpFileSource,
    "rest": RestSource,
}


def make_source(kind, params, secrets, workspace):
    cls = SOURCES.get(kind)
    if not cls:
        raise SourceError("Unknown connection type: %s" % kind)
    return cls(params or {}, secrets or {}, workspace)


# --------------------------------------------------------------------------
# cursor values survive restarts as typed JSON
# --------------------------------------------------------------------------

def encode_cursor(v):
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return {"t": "datetime", "v": v.isoformat()}
    if isinstance(v, datetime.date):
        return {"t": "date", "v": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"t": "decimal", "v": str(v)}
    if isinstance(v, bool):
        return {"t": "int", "v": int(v)}
    if isinstance(v, int):
        return {"t": "int", "v": v}
    if isinstance(v, float):
        return {"t": "float", "v": v}
    return {"t": "str", "v": str(v)}


def decode_cursor(c):
    if not c:
        return None
    t, v = c.get("t"), c.get("v")
    if t == "datetime":
        return datetime.datetime.fromisoformat(v)
    if t == "date":
        return datetime.date.fromisoformat(v)
    if t == "decimal":
        return decimal.Decimal(v)
    if t == "int":
        return int(v)
    if t == "float":
        return float(v)
    return v


def display_cursor(c):
    v = decode_cursor(c)
    if v is None:
        return None
    return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else str(v)


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s[:60] or "source"
