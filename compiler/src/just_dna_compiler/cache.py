"""
Ensembl reference cache resolution — mirrors just-dna-lite's on-disk layout so a marketplace or
standalone compile can **reuse an existing just-dna-lite deployment's cache** (disk economy, no
re-download), pointed via `.env`.

Layout (identical to `just-dna-pipelines`)::

    <base>/ensembl_variations/data/*.parquet
    <base>/ensembl_variations/ensembl_variations.duckdb    # optional prebuilt view

where ``<base>`` is ``$JUST_DNA_PIPELINES_CACHE_DIR`` (the same var just-dna-lite uses), or the
platformdirs user cache for ``"just-dna-pipelines"``. ``$JUST_DNA_ENSEMBL_CACHE`` (a ``.duckdb``
file or a directory) overrides everything for explicit pointing.

This module **never downloads**: if no cache is present, resolution returns ``None`` and the
resolver skips with a warning. Provisioning the reference is the deployment's job.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv
from platformdirs import user_cache_dir

APPNAME: str = "just-dna-pipelines"
ENSEMBL_SUBDIR: str = "ensembl_variations"
DUCKDB_NAME: str = "ensembl_variations.duckdb"


def load_env(override: bool = False) -> Optional[str]:
    """Load the nearest `.env` (walking up from CWD), so cache paths can be set there.
    Returns the loaded path, or None."""
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=override)
        return env_path
    return None


def default_ensembl_cache_dir() -> Path:
    """The `<base>/ensembl_variations` directory, matching just-dna-lite's convention."""
    base = os.getenv("JUST_DNA_PIPELINES_CACHE_DIR")
    root = Path(base) if base else Path(user_cache_dir(appname=APPNAME))
    return root / ENSEMBL_SUBDIR


def resolve_ensembl_reference(
    ensembl_cache: Optional[Path] = None, *, load_dotenv_file: bool = True
) -> Optional[Path]:
    """Locate a usable Ensembl reference without downloading.

    Precedence: explicit `ensembl_cache` → ``$JUST_DNA_ENSEMBL_CACHE`` → the just-dna-lite layout
    under ``$JUST_DNA_PIPELINES_CACHE_DIR`` / platformdirs. Prefers a prebuilt
    ``ensembl_variations.duckdb``; otherwise the directory of parquet files. Returns the resolved
    path (a ``.duckdb`` file or a directory), or ``None`` if nothing is present.
    """
    if load_dotenv_file:
        load_env()

    candidate = ensembl_cache or os.getenv("JUST_DNA_ENSEMBL_CACHE")
    search_dir = Path(candidate) if candidate else default_ensembl_cache_dir()

    # Explicit pointing at a specific DuckDB file.
    if search_dir.is_file() and search_dir.suffix == ".duckdb":
        return search_dir

    # Otherwise return the cache directory if it holds a prebuilt db or parquet data; the
    # connection layer decides whether the db is usable and falls back to parquet if not.
    if search_dir.is_dir():
        data_dir = search_dir / "data"
        has_db = (search_dir / DUCKDB_NAME).is_file()
        has_parquet = (data_dir.is_dir() and any(data_dir.glob("*.parquet"))) or any(
            search_dir.glob("*.parquet")
        )
        if has_db or has_parquet:
            return search_dir
    return None
