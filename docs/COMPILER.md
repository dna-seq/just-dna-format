# Compiler coverage of the 0.3 schema

`just-dna-compiler` adopts the 0.3 schema (`docs/ROADMAP.md` → *Planned for 0.3*) with a
**C++-standard-style feature-coverage** stance: rather than all-or-nothing conformance, it ships a
per-feature table. As of the derivation/round-trip pass the **validator is complete**, the **upgrade
derivation ships** (`state`/booleans → the 0.3 axes, as read-time aliases + a materializing
`upgraded()`), and the artifact **round-trips losslessly including phase**. What remains deferred is
narrow: new *computed stats* and all of 0.4. The derivation functions live in
`just_dna_format.derive` (a `pydantic`-only leaf module), with the row-level `effective_*` accessors,
`upgraded()`, and `needs_upgrade` on `VariantRow`.

Reference consumer semantics: just-dna-lite (`just_dna_pipelines`) derives direction from
`state`/`weight` and tokenizes ClinVar CLNSIG; our columns and derivations are the explicit, tested
form of those.

## Coverage table

| 0.3 feature | Validated | Materialized (→ parquet) | Computed / derived | Status |
|---|---|---|---|---|
| `direction` (`VariantRow`) | ✅ full vocab | ✅ `weights.parquet` | ✅ `effective_direction` / `upgraded()` from `state`(+`weight`) | complete |
| `stat_significance` (`VariantRow`, `StudyRow`) | ✅ full vocab | ✅ | ✅ derived from `state` (not inferred from `p_value`) | complete |
| `effect_size` (`VariantRow`, `StudyRow`) | ✅ float | ✅ | — | complete |
| `effect_measure` (`VariantRow`, `StudyRow`) | ✅ permissive (open) | ✅ | — | complete (intentionally open) |
| `effect_allele` (`VariantRow`) | ✅ nucleotides | ✅ | ⛔ no strand/ref reconciliation (see below) | validate + passthrough |
| `flags` (`VariantRow`) | ✅ open; split; reserved set | ✅ `List[str]` | ✅ unknown-tag INFO (`ValidationResult.info`) | complete |
| `trait_efo_id` (`VariantRow`, `StudyRow`) | ✅ CURIE(s) | ✅ | — | complete |
| `clin_sig` (`VariantRow`) | ✅ full vocab | ✅ | ✅ ↔ `pathogenic`/`benign` aliases (`effective_*` / `upgraded()`) | complete |
| genotype widening: hemizygous single allele | ✅ | ✅ (1-element list) | — | complete |
| genotype widening: phased `A\|G` | ✅ (order kept, not sorted) | ✅ `phased` bit + ordered list → **lossless round-trip** | ✅ | complete |
| `state` (legacy) | ✅ (unchanged, **stays required** — CONSTITUTION P8) | ✅ | ✅ read alias via `effective_direction`; trimmed to {protective,risk,neutral} on `upgraded()` | complete |
| MT / non-diploid genotype | ✅ warning on a two-allele **MT or Y** genotype | — | — | complete |
| direction/weight sign consistency | ✅ warning | — | — | complete |

## Intentionally unimplemented — and why

1. **New computed manifest stats.** `Stats` still carries the 0.2 counts
   (`clinvar_count`/`pathogenic_count`/`benign_count`); no new distributions (e.g. by `direction` or
   `clin_sig`) are computed. The ROADMAP did not require new stats for 0.3, and no consumer needs
   them yet.
2. **`effect_allele` strand/ref reconciliation.** The column is validated (nucleotides) and passed
   through; the compiler does not reconcile it against `ref`/`alts` or normalize strand. The `+`
   strand / `genome_build` assumption is documentation, not an enforced computation.
3. **0.4 materialization** — the diplotype/haplotype, copy-number, repeat, heteroplasmy, activity,
   and PGS tables are **modeled and schema-validated** in `just_dna_format.{binning,pgx,pgs}` (a
   sample implementation; see `schema/tests/test_v04.py` and `docs/REFERENCE_EXAMPLES.md`), but the
   compiler does **not** yet materialize them into parquet — deferred until the shapes freeze after
   round-2 (rebuilding the parquet/round-trip path mid-ping-pong would be wasted). The integration
   points are known and small: add each parquet name to `_OUTPUT_FILES` (which alone wires
   `artifact.digest`), a `_build_binning()`-style builder per the `_build_weights` records+schema
   pattern, source CSVs in `_INPUT_FILES`, and a reverse `_write_*_csv` path in `reverse_module`.
   Because none of that is built yet, **`artifact.digest` is unchanged by the 0.4 sample.**

## 0.4 schema coverage (sample — validated, not yet materialized)

| 0.4 kind (model) | Validated | Materialized (→ parquet) | Status |
|---|---|---|---|
| binning primitive `MeasureBinRow` + `Activity/CopyNumber/RepeatAllele/Heteroplasmy` rows | ✅ shared vocab, inclusive `[min,max]`, mandatory `unresolved`, `extra=forbid`, `source_field` pointer, heteroplasmy `tissue` + legacy-ref guard | ⛔ deferred | schema sample |
| table-level `validate_bins(rows)` (overlap reject / gap warn) | ✅ per `(key…, trait_efo_id)` group | n/a (author-time check) | schema sample |
| PGx `HaplotypeRow` / `AlleleFunctionRow` (star-string verbatim) / `DiplotypeRow` (canonical pair) | ✅ | ⛔ deferred | schema sample |
| PGS `PgsRow` (declared interface; ancestry-validity fields) | ✅ `PGS<digits>`, ancestry/tier vocab, `match_rate∈[0,1]` | ⛔ deferred | schema sample |
| reserved namespace (`caller*`, `requires_callable`, `actionability`, `acmg_sf`) | ✅ rejected via `extra=forbid` until built | — | reserved |

## Upgrade derivation (`state`/booleans → 0.3 axes)

`state` and the ClinVar booleans **stay required/authoritative** for 0.2 backward-compat
(CONSTITUTION Principle 8 — a required field is never demoted to optional inside a major). The new
axes are optional, and `just_dna_format.derive` supplies their fallbacks (per the ROADMAP "Upgrade
derivation" table):

- **Read-time (non-mutating):** `VariantRow.effective_direction` / `effective_stat_significance` /
  `effective_clin_sig` / `effective_pathogenic` / `effective_benign` return the set column, or the
  derivation when it is absent — so a legacy 0.1/0.2 row exposes all three axes with no re-publish.
- **Materializing (for a re-publish):** `VariantRow.upgraded()` returns a copy with those axes filled
  in and `state` trimmed to the legacy set `{protective, risk, neutral}` (kept as a derived mirror of
  `direction`, never dropped). `VariantRow.needs_upgrade` is true when this would change anything —
  the signal the marketplace `revalidate`/`needs_upgrade` drift flow consumes to flag a
  drifted-but-fixable module for a new PATCH. Both are **idempotent** (CONSTITUTION Principle 7).

## Consequences worth knowing

- **`weights.parquet`/`studies.parquet` carry the 0.3 columns** (null-filled when unused) plus a
  `phased` bit, so a re-compile under this compiler changes `artifact.digest` for every module — even
  one that sets no 0.3 column. Expected on a compiler-version bump: reproducibility is pinned by
  `compiler_version`, and already-published versions keep their old digest until re-published. (0.3
  is not yet published, so this digest change is still free to absorb.)
- **Round-trip is lossless and idempotent** (CONSTITUTION Principle 7): `reverse_module` → recompile
  preserves every 0.3 column *including phase* (the `phased` bit re-emits `A|G` vs sorted `A/G`), and
  compiling the same spec twice in a fixed environment yields the same digest.
- The **`ValidationResult.info`** channel carries non-reserved `flags` notes, using stdlib logging
  semantics, **not** Eliot (the format packages do not depend on Eliot).

Tests: `compiler/tests/test_v03.py` exercises the validator, genotype widening, warnings/INFO, and
materialization; `test_v03_roundtrip.py` proves lossless round-trip + digest idempotency; the schema
suite covers the derivation + `upgraded()` idempotency.
