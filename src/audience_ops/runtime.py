"""Owned local PostgreSQL and scoped service identities; never use a production DSN."""
import json
import hashlib
import os
import secrets
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo, conninfo_to_dict

from .client import Client
from .db import connect


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def private_json(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def initialize(admin, folder, receiver_url):
    """Create two fresh databases. Configuration is private, excluded from public evidence."""
    folder = Path(folder)
    info = conninfo_to_dict(admin)
    if info.get("host") not in {"127.0.0.1", "localhost", "postgres"} or info.get("hostaddr"):
        raise ValueError("isolated_local_postgresql_only")
    schema_hash = hashlib.sha256(b"".join(Path(__file__).with_name(n).read_bytes()
                                        for n in ["operating.sql", "receiver.sql"])).hexdigest()
    if (folder / "controller.json").exists():
        config = json.loads((folder / "controller.json").read_bytes())
        if config.get("schema_hash") != schema_hash:
            raise ValueError("schema_revision_changed_requires_explicit_fresh_demo")
        with connect(config["dsn"]) as c:
            c.execute("SELECT 1 FROM brands LIMIT 1")
        return config
    tag = "aud_" + secrets.token_hex(6)
    names = {k: tag + "_" + k for k in ("ops", "receiver", "console")}
    passwords = {k: secrets.token_urlsafe(32) for k in names}
    databases = {"ops": tag + "_ops", "receiver": tag + "_receiver"}
    created = []
    try:
        with psycopg.connect(admin, autocommit=True) as c:
            for role in names:
                c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(names[role]), sql.Literal(passwords[role])))
            for kind, database in databases.items():
                c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
                created.append(database)
                c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
                allowed = [names[kind]] + ([names["console"]] if kind == "ops" else [])
                for role in allowed:
                    c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(role)))
        for kind, database in databases.items():
            with psycopg.connect(make_conninfo(admin, dbname=database)) as c:
                c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                c.execute(Path(__file__).with_name("operating.sql" if kind == "ops" else "receiver.sql").read_text(encoding="utf-8"))
                c.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(names[kind])))
                c.execute(sql.SQL("GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(names[kind])))
                c.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(names[kind])))
                mutable = ["brands", "active", "intents", "heads"] if kind == "ops" else ["membership", "faults"]
                for table in mutable:
                    c.execute(sql.SQL("GRANT UPDATE ON {} TO {}").format(sql.Identifier(table), sql.Identifier(names[kind])))
                if kind == "ops":
                    c.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(names["console"])))
                    c.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(names["console"])))
    except BaseException:
        # Precise owned cleanup; no shared database names are accepted here.
        with psycopg.connect(admin, autocommit=True) as c:
            for database in created:
                c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            for role in names.values():
                c.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        raise
    dsn = {k: make_conninfo(admin, dbname=databases["receiver" if k == "receiver" else "ops"],
                           user=names[k], password=passwords[k]) for k in names}
    read_token, write_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    brands = ["atlas", "nova"]
    config = {"dsn": dsn["ops"], "url": receiver_url, "read_token": read_token, "write_token": write_token,
              "brands": brands, "schema_hash": schema_hash}
    private_json(folder / "receiver.json", {"dsn": dsn["receiver"], "read_token": read_token,
                                            "write_token": write_token, "brands": brands})
    private_json(folder / "console.json", {"dsn": dsn["console"], "url": receiver_url,
                                           "read_token": read_token, "brands": brands})
    private_json(folder / "registry.json", {"roles": list(names.values()), "databases": databases})
    private_json(folder / "controller.json", config)
    return config


class LocalRuntime:
    def __init__(self, workspace):
        self.path = Path(workspace).resolve()
        self.processes = []
        self.own_pg = False
        self.admin = None

    def __enter__(self):
        if self.path.exists():
            raise ValueError("fresh_workspace_required")
        self.path.mkdir(parents=True)
        try:
            self.start()
            return self
        except BaseException:
            self.stop()
            raise

    def start(self):
        self.admin = os.environ.get("OPS_TEST_ADMIN_DSN")
        if not self.admin:
            binary = Path(os.environ.get("PG_BIN", ""))
            suffix = ".exe" if os.name == "nt" else ""
            initdb = shutil.which("initdb") or str(binary / ("initdb" + suffix))
            self.pg_ctl = shutil.which("pg_ctl") or str(binary / ("pg_ctl" + suffix))
            password = secrets.token_urlsafe(32)
            pw = self.path / "install-password"
            pw.write_text(password, encoding="utf-8")
            if os.name != "nt":
                pw.chmod(0o600)
            with (self.path / "initdb.log").open("w") as log:
                subprocess.run([initdb, "-D", str(self.path / "pgdata"), "-U", "postgres", "-A", "scram-sha-256",
                                "--pwfile", str(pw), "--encoding=UTF8", "--locale=C"], stdout=log, stderr=subprocess.STDOUT, check=True)
            pw.unlink()
            port = free_port()
            self.own_pg = True
            # A Windows grandchild can retain pipe handles after pg_ctl exits.
            # Do not wait for EOF from a long-lived server's inherited pipe.
            subprocess.run([self.pg_ctl, "-D", str(self.path / "pgdata"), "-l", str(self.path / "postgres.log"),
                            "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT, check=True, timeout=60)
            self.admin = make_conninfo(host="127.0.0.1", port=port, user="postgres", password=password, dbname="postgres")
        port = free_port()
        self.config = initialize(self.admin, self.path / "private", f"http://127.0.0.1:{port}")
        self.receiver_config = json.loads((self.path / "private/receiver.json").read_bytes())
        self.client = Client(self.config["url"], self.config["read_token"], self.config["write_token"])
        self.spawn("receiver", self.path / "private/receiver.json", port)
        for _ in range(100):
            try:
                if self.client.request("/health")[0] == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("receiver_start_failed; inspect private service log")

    def spawn(self, service, config, port):
        log = (self.path / (service + ".log")).open("w", encoding="utf-8")
        child = subprocess.Popen([sys.executable, "-m", "audience_ops.service", service, "--config", str(config),
                                  "--port", str(port)], stdout=log, stderr=subprocess.STDOUT)
        self.processes.append((child, log))
        return child

    def stop(self):
        for child, log in reversed(self.processes):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
            log.close()
        if self.admin and (self.path / "private/registry.json").exists():
            registry = json.loads((self.path / "private/registry.json").read_bytes())
            if not all(re.fullmatch(r"aud_[a-f0-9]{12}_(ops|receiver|console)", n)
                       for n in [*registry["roles"], *registry["databases"].values()]):
                raise ValueError("owned_cleanup_registry_invalid")
            with psycopg.connect(self.admin, autocommit=True) as c:
                for database in registry["databases"].values():
                    c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
                for role in registry["roles"]:
                    c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        if self.own_pg:
            subprocess.run([self.pg_ctl, "-D", str(self.path / "pgdata"), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True, timeout=60)

    def __exit__(self, *_):
        self.stop()
