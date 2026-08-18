"""Accès PostgreSQL via psycopg2 et un ThreadedConnectionPool.

Tout le code d'accès aux données est synchrone. Les endpoints FastAPI déclarés
`def` (et non `async def`) sont exécutés par Starlette dans un threadpool, ce qui
convient parfaitement à un pool de connexions threadé. Les endpoints réellement
asynchrones (streaming LLM) enveloppent leurs accès BDD dans `asyncio.to_thread`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from .config import settings

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_pool() -> ThreadedConnectionPool:
    """Singleton paresseux : le pool est créé au premier accès."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    minconn=settings.db_pool_min,
                    maxconn=settings.db_pool_max,
                    dsn=settings.database_url,
                    # `connect_timeout` évite qu'un déploiement Railway se bloque
                    # indéfiniment si la base n'est pas encore prête.
                    connect_timeout=10,
                )
                logger.info(
                    "Pool PostgreSQL créé (min=%s, max=%s)",
                    settings.db_pool_min,
                    settings.db_pool_max,
                )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Pool PostgreSQL fermé")


@contextmanager
def connection(commit: bool = True) -> Iterator[psycopg2.extensions.connection]:
    """Emprunte une connexion au pool et la rend systématiquement."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def cursor(commit: bool = True) -> Iterator[psycopg2.extras.RealDictCursor]:
    """Curseur renvoyant des dictionnaires (RealDictCursor)."""
    with connection(commit=commit) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur


# --- Helpers de requête ------------------------------------------------------


def query_all(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict]:
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> dict | None:
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> int:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_returning(
    sql: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> dict | None:
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute_all_returning(
    sql: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> list[dict]:
    """Écrit et renvoie **toutes** les lignes touchées, en validant la transaction.

    Ce qui manquait, et le piège que son absence a coûté : `query_all` s'exécute
    avec `commit=False`, parce qu'il est fait pour lire. Un `UPDATE ... RETURNING`
    passé par lui renvoie bien les lignes — le curseur les a produites — puis la
    connexion est rendue au pool sans validation, et l'écriture est perdue. Le
    symptôme est trompeur : la fonction a l'air de marcher, elle ne persiste rien.
    """
    with cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# --- pgvector ---------------------------------------------------------------


def to_halfvec(embedding: Sequence[float]) -> str:
    """Sérialise un embedding au format littéral pgvector.

    On passe par le littéral textuel `'[0.1,0.2,...]'` avec un cast SQL
    `::halfvec` plutôt que par un type adapté : cela évite toute dépendance à la
    version du paquet `pgvector` côté client et fonctionne avec halfvec comme
    avec vector.
    """
    return "[" + ",".join(f"{float(x):.7g}" for x in embedding) + "]"


# --- Initialisation ---------------------------------------------------------


def init_db() -> None:
    """Applique schema.sql (idempotent) au démarrage."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("Schéma appliqué")


def healthcheck() -> dict[str, Any]:
    out: dict[str, Any] = {"database": "down", "pgvector": False, "kb_chunks": 0}
    try:
        row = query_one(
            "SELECT (SELECT count(*) FROM pg_extension WHERE extname = 'vector') AS ext"
        )
        out["database"] = "up"
        out["pgvector"] = bool(row and row["ext"])
        chunks = query_one("SELECT count(*) AS n FROM kb_chunks")
        out["kb_chunks"] = int(chunks["n"]) if chunks else 0
        embedded = query_one("SELECT count(*) AS n FROM kb_chunks WHERE embedding IS NOT NULL")
        out["kb_chunks_embedded"] = int(embedded["n"]) if embedded else 0
    except Exception as exc:  # pragma: no cover - diagnostic
        out["error"] = str(exc)
    return out
