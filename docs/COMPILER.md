# Compiler coverage of the 0.3 + 0.4 schema

`just-dna-compiler` adopts the schema (`docs/ROADMAP.md`, `docs/PROPOSAL_0_4.md`) with a
**C++-standard-style feature-coverage** stance: rather than all-or-nothing conformance, it ships a
per-feature table. As of the 0.4 materialization pass the **validator is complete**, the **upgrade
derivation ships** (`state`/booleans → the 0.3 axes, as read-time aliases + a materializing
`upgraded()`), the artifact **round-trips losslessly including phase**, and **all nine 0.4 table
kinds materialize with enforced table-level coherence** (see the 0.4 section below). What remains
deferred is narrow: new *computed stats*. The derivation functions live in
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
3. **0.4 materialization — DONE (RM1 + RM2).** The diplotype/haplotype, copy-number, repeat,
   heteroplasmy, activity, PGS, and PharmGKB tables now **materialize to parquet with lossless
   round-trip** via a generic model-driven materializer (`_build_table`/`_write_table_csv`, driven by
   each model's `model_fields`), registered in `_TABLE_KINDS`. A module **composes from optional table
   kinds** (RM2): the only always-present file is `module_spec.yaml`; `variants.csv` is optional, and a
   module with no variants (a PGx/PharmGKB/PRS-only module) compiles and reverses without an empty
   `variants.csv`. Grounding (`studies.csv`) is required iff `variants.csv` is present. **`artifact.digest`
   moved once** off the old `weights`-only value because `weights.parquet` gained the three 0.4
   `VariantRow` axes — expected (0.4 unpublished); determinism + round-trip are the held invariants.

## 0.4 compiler coverage (materialized)

| 0.4 kind (model) | Validated | Materialized (→ parquet, round-trip) | Status |
|---|---|---|---|
| binning primitive `MeasureBinRow` + `Activity/CopyNumber/RepeatAllele/Heteroplasmy` rows | ✅ shared vocab, inclusive `[min,max]`, mandatory `unresolved`, `extra=forbid`, `source_field` pointer, heteroplasmy `tissue` + legacy-ref guard | ✅ `*.parquet` via generic materializer | **materialized** |
| table-level `validate_bins(rows)` (overlap reject / gap warn) | ✅ per `(key…, trait_efo_id)` group | **enforced in `validate_spec`**: overlap → error, gap → warning, >1 `unresolved` sentinel/group → error | **enforced** |
| duplicate-row detection (diplotype pair, `pgs_id`, `(pharm variant, drug)`, allele-function allele, haplotype-defining variant) | ✅ per-kind natural key | **enforced in `validate_spec`** → error (0.4 analog of duplicate-(variant, genotype)) | **enforced** |
| PGx `HaplotypeRow` / `AlleleFunctionRow` (star-string verbatim) / `DiplotypeRow` (+ `drug`/`response`/`evidence_level`) | ✅ | ✅ | **materialized** |
| PharmGKB `PharmVariantRow` (`pharm_variants.csv`; single-variant drug response, `evidence_level` 1A…4) | ✅ | ✅ | **materialized** |
| `VariantRow` general axes: `requires_callable` / `acmg_sf` / `actionability` (optional) | ✅ (`actionability` vs `ACTIONABILITY_SEED`) | ✅ into `weights.parquet` (bespoke; tri-state bool round-trip) | **materialized** |
| PGS `PgsRow` (declared interface; ancestry-validity fields) | ✅ `PGS<digits>`, ancestry/tier vocab, `match_rate_floor∈[0,1]` | ✅ | **materialized** |
| reserved namespace (`caller` / `caller_version` / `reference_db` / `callable_from`) | ✅ rejected via `extra=forbid` until built | — | reserved |
| authoring reference + palette (`reference.authoring_reference()`/`json_schemas()`, `RECOMMENDED_COLORS`/`RECOMMENDED_ICONS`) | ✅ generated from the live models (drift-proof) | n/a (schema helper) | **shipped** (RM8/RM9) |

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
  `compiler_version`, and already-published versions keep their old digest until re-published. The
  0.4.0 round-trip fixes moved the digest again for some modules — `annotations.parquet` gained a
  `variant_key` column, `studies.parquet` gained `chrom`/`start`/`ref`, and the ClinVar booleans are
  now null instead of `False` when unset. (0.4 is not yet published, so these digest changes are
  still free to absorb.)
- **Round-trip is lossless and idempotent** (CONSTITUTION Principle 7): `reverse_module` → recompile
  preserves every 0.3 column *including phase* (the `phased` bit re-emits `A|G` vs sorted `A/G`), and
  compiling the same spec twice in a fixed environment yields the same digest. This now holds for the
  shapes an earlier pass got wrong (0.4.0 fixes, all regression-tested): **position-only** variants
  (annotations keyed by `variant_key`, not the null `rsid`) and **position-only study rows**
  (`studies.parquet` carries `chrom`/`start`/`ref`, so a reversed row keeps an identifier and
  recompiles); a partially-set **`priority`** is written verbatim, not fabricated from the mode; and
  the ClinVar booleans (`clinvar`/`pathogenic`/`benign`) are **tri-state** (nullable), so an authored
  `False` survives instead of collapsing to `None`.
- The **`ValidationResult.info`** channel carries non-reserved `flags` notes, using stdlib logging
  semantics, **not** Eliot (the format packages do not depend on Eliot).

Tests: `compiler/tests/test_v03.py` exercises the validator, genotype widening, warnings/INFO, and
materialization; `test_v03_roundtrip.py` proves lossless round-trip + digest idempotency; the schema
suite covers the derivation + `upgraded()` idempotency.
