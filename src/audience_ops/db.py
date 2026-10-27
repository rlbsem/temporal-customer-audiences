from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from temporal_audiences.contracts import Refused


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    brands: frozenset[str]
    streams: frozenset[str] = frozenset()

    def require(self, brand, roles):
        if brand not in self.brands or self.role not in roles:
            raise Refused("scope_or_role_denied")


@contextmanager
def connect(dsn):
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        c.execute("SET statement_timeout='20s'")
        c.execute("SET lock_timeout='5s'")
        yield c


def lock(c, brand):
    # Serialize policy/publication and sender authorization for a single brand.
    c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (brand,))


def audit(c, brand, actor, action, reference, body):
    c.execute("INSERT INTO audit(brand,actor,action,reference,body) VALUES(%s,%s,%s,%s,%s)",
              (brand, actor, action, reference, Jsonb(body)))
