"""
Bidirectional rsid <-> position resolver using an Ensembl DuckDB (GRCh38).

Unlike the original pipelines resolver, this standalone version **injects** the Ensembl
reference: the caller passes either a prebuilt `.duckdb` file or a directory of Ensembl parquet
files, and the resolver builds an ephemeral `ensembl_variations` view over it. It never reaches
into `just-dna-pipelines` and never downloads anything — provisioning the reference is the
caller's responsibility (the marketplace pins one reference for the whole ecosystem).
"""

import logging
from pathlib import Path
from typing import Optional

import duckdb

from just_dna_format.spec import VariantRow

from just_dna_compiler.cache import DUCKDB_NAME, resolve_ensembl_reference

logger = logging.getLogger(__name__)


class EnsemblReferenceError(FileNotFoundError):
    """Raised when a provided Ensembl reference is neither a usable .duckdb nor a parquet dir."""


def _has_ensembl_table(con: duckdb.DuckDBPyConnection) -> bool:
    return any(r[0] == "ensembl_variations" for r in con.execute("SHOW TABLES").fetchall())


def _view_over_parquet(reference: Path) -> Optional[duckdb.DuckDBPyConnection]:
    """Build an in-memory `ensembl_variations` view over the cache's parquet files, or None."""
    parquet_glob: Optional[Path] = None
    if (reference / "data").is_dir() and any((reference / "data").glob("*.parquet")):
        parquet_glob = reference / "data"
    elif reference.is_dir() and any(reference.glob("*.parquet")):
        parquet_glob = reference
    if parquet_glob is None:
        return None
    # DuckDB can't bind a parameter inside CREATE VIEW ... read_parquet(). The pattern is a local
    # path from our own cache resolution, not user input; single-quote-escape it defensively.
    pattern = f"{parquet_glob}/*.parquet".replace("'", "''")
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW ensembl_variations AS SELECT * FROM read_parquet('{pattern}')")
    return con


def _connect(reference: Path) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection exposing an `ensembl_variations` relation.

    `reference` (from `resolve_ensembl_reference`) is a `.duckdb` file or a cache directory. A
    prebuilt DuckDB is used only if it actually contains the `ensembl_variations` table (a stale/
    empty db, as just-dna-lite may leave behind, is ignored in favor of the parquet `data/`).
    """
    reference = Path(reference)

    if reference.is_file() and reference.suffix == ".duckdb":
        con = duckdb.connect(str(reference), read_only=True)
        if _has_ensembl_table(con):
            return con
        con.close()
        raise EnsemblReferenceError(f"{reference} has no ensembl_variations table")

    db = reference / DUCKDB_NAME
    if db.is_file():
        con = duckdb.connect(str(db), read_only=True)
        if _has_ensembl_table(con):
            return con
        con.close()  # empty/stale prebuilt db — fall back to parquet

    con = _view_over_parquet(reference)
    if con is None:
        raise EnsemblReferenceError(f"no usable Ensembl .duckdb or parquet files at {reference}")
    return con


def resolve_variants(
    variants: list[VariantRow],
    ensembl_cache: Optional[Path] = None,
) -> tuple[list[VariantRow], list[str]]:
    """Fill in missing rsid or position from the injected Ensembl reference (GRCh38).

    Variants that already carry both identifiers are returned unchanged. If no reference is
    available, resolution is skipped with a warning rather than raising.
    """
    need_pos = [v for v in variants if v.rsid is not None and v.chrom is None]
    need_rsid = [v for v in variants if v.rsid is None and v.chrom is not None]
    if not need_pos and not need_rsid:
        return variants, []

    reference = resolve_ensembl_reference(ensembl_cache)
    if reference is None:
        msg = (
            "Ensembl resolution skipped: no reference cache found "
            "(set JUST_DNA_PIPELINES_CACHE_DIR or JUST_DNA_ENSEMBL_CACHE, or pass ensembl_cache)"
        )
        logger.warning(msg)
        return variants, [msg]

    try:
        con = _connect(reference)
    except EnsemblReferenceError as exc:
        msg = f"Ensembl resolution skipped: {exc}"
        logger.warning(msg)
        return variants, [msg]

    warnings: list[str] = []
    rsid_to_pos: dict[str, dict] = {}
    if need_pos:
        unique_rsids = list({v.rsid for v in need_pos if v.rsid is not None})
        rsid_to_pos = _lookup_positions_by_rsid(con, unique_rsids, warnings)
    pos_to_rsid: dict[str, str] = {}
    if need_rsid:
        unique_positions = list(
            {(v.chrom, v.start, v.ref) for v in need_rsid if v.chrom is not None and v.start is not None}
        )
        pos_to_rsid = _lookup_rsids_by_position(con, unique_positions, warnings)
    con.close()

    patched: list[VariantRow] = []
    for v in variants:
        if v.rsid is not None and v.chrom is None and v.rsid in rsid_to_pos:
            patched.append(v.model_copy(update=rsid_to_pos[v.rsid]))
        elif v.rsid is None and v.chrom is not None:
            key = f"{v.chrom}:{v.start}:{v.ref}"
            if key in pos_to_rsid:
                patched.append(v.model_copy(update={"rsid": pos_to_rsid[key]}))
            else:
                warnings.append(f"Position {key}: no rsid found in Ensembl")
                patched.append(v)
        else:
            patched.append(v)
    return patched, warnings


def _lookup_positions_by_rsid(
    con: duckdb.DuckDBPyConnection, rsids: list[str], warnings: list[str]
) -> dict[str, dict]:
    """Batch lookup: rsid -> {chrom, start, ref, alts}."""
    if not rsids:
        return {}
    placeholders = ", ".join("?" for _ in rsids)
    rows = con.execute(
        f"""
        SELECT id, chrom, start, ref, string_agg(DISTINCT alt, ',' ORDER BY alt) AS alts
        FROM ensembl_variations
        WHERE id IN ({placeholders})
        GROUP BY id, chrom, start, ref
        """,
        rsids,
    ).fetchall()
    result: dict[str, dict] = {}
    for row_id, chrom, start, ref, alts in rows:
        if row_id in result:
            continue
        result[row_id] = {"chrom": str(chrom), "start": int(start), "ref": str(ref), "alts": str(alts)}
    for rsid in rsids:
        if rsid not in result:
            warnings.append(f"{rsid}: not found in Ensembl, position remains unset")
    return result


def _lookup_rsids_by_position(
    con: duckdb.DuckDBPyConnection,
    positions: list[tuple[Optional[str], Optional[int], Optional[str]]],
    warnings: list[str],
) -> dict[str, str]:
    """Batch lookup: (chrom, start, ref) -> rsid."""
    if not positions:
        return {}
    conditions = []
    params: list[object] = []
    for chrom, start, ref in positions:
        if ref is not None:
            conditions.append("(chrom = ? AND start = ? AND ref = ?)")
            params.extend([chrom, start, ref])
        else:
            conditions.append("(chrom = ? AND start = ?)")
            params.extend([chrom, start])
    where = " OR ".join(conditions)
    rows = con.execute(
        f"SELECT DISTINCT chrom, start, ref, id FROM ensembl_variations "
        f"WHERE ({where}) AND id LIKE 'rs%'",
        params,
    ).fetchall()
    result: dict[str, str] = {}
    for chrom, start, ref, row_id in rows:
        key = f"{chrom}:{start}:{ref}"
        if key not in result:
            result[key] = str(row_id)
    return result
