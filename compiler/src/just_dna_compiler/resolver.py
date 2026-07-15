"""
Bidirectional rsid <-> position resolver using an Ensembl DuckDB (GRCh38).

Unlike the original pipelines resolver, this standalone version **injects** the Ensembl
reference: the caller passes either a prebuilt `.duckdb` file or a directory of Ensembl parquet
files, and the resolver builds an ephemeral `ensembl_variations` view over it. It never reaches
into `just-dna-pipelines` and never downloads anything — provisioning the reference is the
caller's responsibility (the marketplace pins one reference for the whole ecosystem).
"""

import logging
from collections import defaultdict
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
    genome_build: str = "GRCh38",
) -> tuple[list[VariantRow], list[str]]:
    """Fill in missing rsid or position from the injected Ensembl reference (GRCh38).

    Variants that already carry both identifiers are returned unchanged. If no reference is
    available, resolution is skipped with a warning rather than raising.

    **One-to-many rsid → expansion.** A no-coord rsid that maps to several loci is expanded into one
    row per locus, each re-keyed to its coordinate (`variant_key`), so the N loci get N distinct
    identities — a paralog/SV signal a consumer can count (data-agnostic). A 1:1 rsid just fills the
    coordinate and keeps its rsid key. `variant_key` is frozen (`base.derive_variant_key`), so filling
    a coord/rsid never re-keys a row (Principle 7); only expansion reassigns it.

    **GRCh38-bound.** The reference is GRCh38, so resolution runs only for a GRCh38 module; a
    GRCh37/T2T build is skipped with a warning (positions are not re-resolved cross-build — RM15),
    rather than corrupting coordinates against the wrong assembly.

    **Bidirectional consistency (inject-only, no network).** For rows that authored *both* an rsid and
    a coordinate, the same injected reference is used to check that the coordinate is among the rsid's
    loci and the rsid among the coordinate's ids; a disagreement is a **warning** (it may be a dbSNP
    merge/build difference — never fatal, matching the resolver's best-effort stance).
    """
    if genome_build != "GRCh38":
        msg = (
            f"Ensembl resolution skipped: compiler is GRCh38-bound, module genome_build is "
            f"{genome_build!r} — positions are not re-resolved cross-build (RM15)."
        )
        logger.warning(msg)
        return variants, [msg]

    need_pos = [v for v in variants if v.rsid is not None and v.chrom is None]
    need_rsid = [v for v in variants if v.rsid is None and v.chrom is not None]
    verify = [
        v for v in variants
        if v.rsid is not None and v.chrom is not None and v.start is not None
    ]
    if not need_pos and not need_rsid and not verify:
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
    rsid_to_pos: dict[str, list[dict]] = {}
    if need_pos:
        unique_rsids = list({v.rsid for v in need_pos if v.rsid is not None})
        rsid_to_pos = _lookup_positions_by_rsid(con, unique_rsids, warnings)
    pos_to_rsid: dict[str, str] = {}
    if need_rsid:
        unique_positions = list(
            {(v.chrom, v.start, v.ref) for v in need_rsid if v.chrom is not None and v.start is not None}
        )
        pos_to_rsid = _lookup_rsids_by_position(con, unique_positions, warnings)
    if verify:
        _check_rsid_coord_consistency(con, verify, warnings)
    con.close()

    patched: list[VariantRow] = []
    for v in variants:
        if v.rsid is not None and v.chrom is None and v.rsid in rsid_to_pos:
            loci = rsid_to_pos[v.rsid]
            if len(loci) == 1:
                # 1:1 — fill the coordinate; the frozen variant_key stays the rsid.
                patched.append(v.model_copy(update=loci[0]))
            else:
                # One-to-many — expand to one coord-keyed row per locus (deterministic order from the
                # ORDER BY). Each row re-keys variant_key to its coordinate so the loci are distinct.
                warnings.append(
                    f"{v.rsid} maps to {len(loci)} loci in Ensembl; expanded to {len(loci)} rows "
                    f"(one per locus, each keyed by its coordinate — a consumer can count them)."
                )
                for locus in loci:
                    key = f"{locus['chrom']}:{locus['start']}:{locus['ref']}"
                    patched.append(v.model_copy(update={**locus, "variant_key": key}))
        elif v.rsid is None and v.chrom is not None:
            key = f"{v.chrom}:{v.start}:{v.ref}"
            if key in pos_to_rsid:
                # Fill the rsid; the frozen variant_key stays the coordinate (no flip).
                patched.append(v.model_copy(update={"rsid": pos_to_rsid[key]}))
            else:
                warnings.append(f"Position {key}: no rsid found in Ensembl")
                patched.append(v)
        else:
            patched.append(v)
    return patched, warnings


def _lookup_positions_by_rsid(
    con: duckdb.DuckDBPyConnection, rsids: list[str], warnings: list[str]
) -> dict[str, list[dict]]:
    """Batch lookup: rsid -> [{chrom, start, ref, alts}, ...] (ALL loci, deterministically ordered).

    An rsid can map to several loci (paralogs, patch/haplotype scaffolds, PAR). Every locus is
    returned — the caller expands a one-to-many rsid into one row per locus rather than picking one
    (a silent "first-met" pick was non-deterministic and dropped real loci). `ORDER BY id, chrom,
    start, ref` makes the emitted order stable across runs (idempotency, Principle 7)."""
    if not rsids:
        return {}
    placeholders = ", ".join("?" for _ in rsids)
    rows = con.execute(
        f"""
        SELECT id, chrom, start, ref, string_agg(DISTINCT alt, ',' ORDER BY alt) AS alts
        FROM ensembl_variations
        WHERE id IN ({placeholders})
        GROUP BY id, chrom, start, ref
        ORDER BY id, chrom, start, ref
        """,
        rsids,
    ).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for row_id, chrom, start, ref, alts in rows:
        result[row_id].append(
            {"chrom": str(chrom), "start": int(start), "ref": str(ref), "alts": str(alts)}
        )
    for rsid in rsids:
        if rsid not in result:
            warnings.append(f"{rsid}: not found in Ensembl, position remains unset")
    return dict(result)


def _check_rsid_coord_consistency(
    con: duckdb.DuckDBPyConnection, rows: list[VariantRow], warnings: list[str]
) -> None:
    """Warn (never fail) when an authored rsid↔coordinate pair disagrees with the injected reference.

    For each row carrying both an rsid and a coordinate: verify the coordinate is among the rsid's
    loci AND the rsid is among the coordinate's dbSNP ids. A contradiction is a warning (it may be a
    dbSNP merge or a reference-build difference); when the reference knows neither side, the pair is
    left unverified (skipped). Inject-only — the same reference the resolver already opened, no
    network (Constitution Principle 2)."""
    rsid_loci = _lookup_positions_by_rsid(con, list({r.rsid for r in rows}), [])
    rsid_coordkeys: dict[str, set[str]] = {
        rsid: {f"{lo['chrom']}:{lo['start']}:{lo['ref']}" for lo in loci}
        for rsid, loci in rsid_loci.items()
    }
    positions = list({(r.chrom, r.start, r.ref) for r in rows})
    coord_ids = _lookup_rsid_sets_by_position(con, positions)

    for r in rows:
        coordkey = f"{r.chrom}:{r.start}:{r.ref}"
        loci = rsid_coordkeys.get(r.rsid)
        ids = coord_ids.get(coordkey)
        if loci and coordkey not in loci:
            warnings.append(
                f"{r.rsid} authored at {coordkey}, but Ensembl maps {r.rsid} to {sorted(loci)} "
                f"(reference disagreement — may be a dbSNP merge/build difference)."
            )
        elif ids and r.rsid not in ids:
            warnings.append(
                f"{coordkey} authored as {r.rsid}, but Ensembl reports {sorted(ids)} there "
                f"(reference disagreement — may be a dbSNP merge/build difference)."
            )


def _lookup_rsid_sets_by_position(
    con: duckdb.DuckDBPyConnection,
    positions: list[tuple[Optional[str], Optional[int], Optional[str]]],
) -> dict[str, set[str]]:
    """Batch lookup: `chrom:start:ref` -> set of dbSNP ids at that exact position."""
    concrete = [(c, s, ref) for c, s, ref in positions if c is not None and s is not None]
    if not concrete:
        return {}
    conditions = " OR ".join("(chrom = ? AND start = ? AND ref = ?)" for _ in concrete)
    params: list[object] = []
    for chrom, start, ref in concrete:
        params.extend([chrom, start, ref])
    rows = con.execute(
        f"SELECT DISTINCT chrom, start, ref, id FROM ensembl_variations "
        f"WHERE ({conditions}) AND id LIKE 'rs%'",
        params,
    ).fetchall()
    result: dict[str, set[str]] = defaultdict(set)
    for chrom, start, ref, row_id in rows:
        result[f"{chrom}:{start}:{ref}"].add(str(row_id))
    return dict(result)


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
        f"WHERE ({where}) AND id LIKE 'rs%' "
        # ORDER BY makes the pick deterministic when a position is multi-allelic: two runs against the
        # same DB resolve a ref-less position to the same id, so `resolve_with_ensembl` stays idempotent.
        f"ORDER BY chrom, start, ref, id",
        params,
    ).fetchall()
    # A ref-less input position (ref=None) matched on (chrom, start) only, so the caller's lookup key
    # is `chrom:start:None` — it can never equal a DB key carrying the concrete ref. Register such
    # positions under the ref-less key too, so a position-only-without-ref variant resolves.
    refless = {(str(c), s) for c, s, r in positions if r is None}
    result: dict[str, str] = {}
    refless_warned: set[tuple[str, int]] = set()
    for chrom, start, ref, row_id in rows:
        full = f"{chrom}:{start}:{ref}"
        result.setdefault(full, str(row_id))
        pos = (str(chrom), start)
        if pos in refless:
            refless_key = f"{chrom}:{start}:None"
            if refless_key not in result:
                result[refless_key] = str(row_id)
            elif result[refless_key] != str(row_id) and pos not in refless_warned:
                # A multi-allelic site: the ref-less key already resolved to a different id. The
                # ORDER BY fixes which one wins, but the choice is genuinely ambiguous — surface it.
                refless_warned.add(pos)
                warnings.append(
                    f"{chrom}:{start} (ref unspecified) matches multiple dbSNP ids; resolved to "
                    f"{result[refless_key]} deterministically — specify ref to disambiguate."
                )
    return result
