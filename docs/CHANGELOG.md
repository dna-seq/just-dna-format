# Changelog

Shared change log for the just-dna module format/compiler ecosystem. Because
`just-dna-format` + `just-dna-compiler` are consumed by **just-dna-pipelines**,
**just-dna-marketplace**, and **just-dna-agents**, cross-repo integration changes are recorded
here so parallel work in the other repos isn't surprised. Newest first.

## 2026-07-15 — 0.4.0 (unpublished) — frozen variant identity + one-to-many rsid expansion

A follow-up correctness pass on the 0.4 branch, resolving an identity-model flaw the branch review
surfaced (still unpublished, so the `artifact.digest` move is free). Root cause: `variant_key =
rsid-else-coord` treated an rsid and a coordinate as interchangeable identities, so the Ensembl
resolver — an enrichment — *mutated identity* (filling a coord→rsid flipped the derived key; a
one-to-many rsid had no faithful representation), silently breaking round-trip/idempotency
(Principle 7) and collapsing `annotations.parquet` dedup.

- **Frozen `variant_key` (minimal B+).** `VariantRow.variant_key` is now a stored column (via
  `base.derive_variant_key`), stamped once at load — rsid when it uniquely identifies the row, else
  the coordinate — and never re-derived; a `model_copy` does not re-run the validator, so resolution
  can fill a coord/rsid or expand a row without ever re-keying it. Materialized into
  `weights.parquet`; **compiler-managed** — excluded from `authoring_reference()` and never written
  back by `reverse_module`. `StudyRow`/`PharmVariantRow` keep the derived property (never resolved).
- **One-to-many rsid → row expansion.** A no-coord rsid that resolves to N>1 loci now expands into N
  coord-keyed rows (a paralog/SV signal a consumer can count — data-agnostic), instead of a
  non-deterministic "first-met" pick. `_lookup_positions_by_rsid` gained `ORDER BY id, chrom, start,
  ref` and returns all loci. Compiler behavior pinned by `compiler_version` (P4), GRCh38-only.
- **`reverse_module` restores authored shape** by reading the frozen key: an rsid-keyed row emits its
  rsid; a coord-keyed row (rsid was *resolved*, or position-only/expanded) emits **position-only**,
  dropping the resolved rsid — so field-only recompute + re-resolution reproduce the same key. No new
  CSV column; reverse→recompile is a digest fixed point (proven for the position-only→rsid and
  expansion shapes).
- **Bidirectional rsid↔coord consistency check** against the **injected** reference (inject-only, no
  network — Principle 2, same pattern as the resolver): a disagreement is a **warning** (may be a
  dbSNP merge/build difference), never fatal.
- **GRCh38-bound reality made explicit.** Resolution is skipped with a warning for a non-GRCh38
  `genome_build` (positions are not re-resolved cross-build — RM15) rather than corrupting
  coordinates against the wrong assembly; documented on `genome_build`, in COMPILER.md, and as
  ROADMAP RM15 + the "additivity has two axes" note.
- **Audit fixes.** Studies orphan check matches on a shared identifier (rsid *or* coord), not
  frozen-key equality; the position-consistency check compares only positioned rows (no
  mixed-authoring false positive); a malformed `provenance.json` / unsupported logo returns
  `CompilationResult(success=False)` instead of raising mid-compile; stale docs corrected
  (`COMPILER.md` reserved-namespace row, compiler `__init__` "three-parquet"); dead `or v` tails
  dropped. **Tests +20** (frozen-key freeze/backfill/reference-exclusion, resolver expansion +
  determinism + consistency + build-skip, compile→reverse→recompile flip-prevention + expansion
  idempotency, old-artifact fallback, orphan-on-coord, malformed-provenance).

## 2026-07-15 — 0.4.0 (unpublished) — branch-review fixes

A second correctness/consistency pass over the 0.4 branch before publish (still unpublished, so all
of the below is free to absorb). Each fix ships with a regression test.

- **PGx diplotypes with multiple drug annotations now compile.** The per-table duplicate-row key for
  `DiplotypeRow` omitted `drug`, so two legitimate rows for one haplotype pair differing only by drug
  (e.g. CYP2D6 `*1/*1` → codeine and → tramadol) were wrongly rejected as duplicates and the whole
  module failed to compile. The key now includes `drug` (matching its own comment and the intended
  authoring pattern). `HaplotypeRow`'s key likewise gained `ref`, so two position-only defining
  variants at the same locus differing only by reference allele no longer false-collide.
- **Reserved-namespace enforcement extended to the SNP core.** `VariantRow`/`StudyRow` now enforce
  `extra="forbid"` (via the shared `AuthoredModel` base below), matching the 0.4 composed tables — the
  ROADMAP tracker previously scoped rejection to "the 0.4 tables" only, so the core defaulted to
  `extra="ignore"` and a genuinely-reserved name (or a misspelled column like `directon`) was silently
  dropped rather than rejected. Now caught at validate time. A **hardening** in the spirit of
  CONSTITUTION P5 (reserve names so they survive the one-way door) + P3 (names permanent within a
  major) — the charter mandates reserve+audit, not runtime rejection, so this is a strengthening, not a
  charter-forced fix.
- **The reserved list now has build-time teeth, not just a published dictionary.** A `reject_reserved`
  before-validator (`vocab.py`), layered on `extra="forbid"` on every authored model, makes a reserved
  name fail with a *specific* diagnosis — what the name is reserved for (`vocab.RESERVED_NAME_REASONS`)
  and that a future release may claim it — while a random or misspelled column still gets the generic
  "extra inputs not permitted". So `reference_db` ≠ `xyzzy` at the point of failure, at author time and
  in the compile errors, for both a human and an authoring agent. Previously the frozenset drove no
  validation behavior at all (consulted only by `authoring_reference()`); now reserved vs. arbitrary is
  a real distinction the maintainer's list produces.
- **Reserved set corrected: `caller`/`caller_version` dropped, `reference_db` re-scoped.** The
  "provenance triple" (round-2 Q2, PROPOSAL_0_4 §T2) was a category error: `caller`/`caller_version`
  name which tool produced a *call* — a consumer-side measurement the module never holds — so there is
  no anticipated module axis to reserve, and barring the bare name is arbitrary (one non-feature among
  unbounded non-features; `extra="forbid"` already rejects them generically). They are removed from
  `RESERVED_NAMES_0_4`, which is now *only* genuine anticipated module axes: **`reference_db`** —
  re-scoped to its real module-side meaning, a hint naming which reference DB the app should join an
  annotation against (implicit Ensembl/ClinVar today; pinnable per module) — and **`callable_from`**
  (RM6). PROPOSAL_0_4 §T2 carries a superseded note.
- **DRY: single `AuthoredModel` base** (`base.py`). The reserved-namespace guard (`extra="forbid"` +
  `reject_reserved`) and the field validators for the shared authored vocabulary (`rsid`,
  `trait_efo_id`, `direction`, `clin_sig`, `stat_significance`, `evidence_level`, finite-`effect_size`)
  were copy-pasted across `spec`/`binning`/`pgx`/`pgs` (~22 duplicated validators + 8 `model_config` +
  8 guards). They now live once on `AuthoredModel`; each row model inherits it and keeps only its
  field-specific rules (genotype/phase, star-allele strings, measure bounds, PGS ancestry, the mtDNA
  legacy-reference guard, identifier completeness). `check_fields=False` means a validator runs only
  for the fields a subclass actually declares, so per-field rules can no longer drift model-to-model.
- **Deterministic ref-less rsid resolution.** In the inject-a-reference path, a ref-less position over
  a multi-allelic dbSNP site was resolved to whichever row the DB returned first (no `ORDER BY`) — a
  latent idempotency risk, silent. It now resolves deterministically and emits an ambiguity warning
  telling the author to specify `ref` to disambiguate.
- **Doc/comment consistency:** the compiler module docstring now describes the composed multi-parquet
  artifact (not a fixed three-parquet one); the COMPILER.md coverage header reads "0.3 / 0.4 feature"
  and its dangling "Upgrade derivation" ROADMAP pointer is removed; the ROADMAP 0.5-scope table no
  longer describes its shipped ✅ rows as "still open"; `just-dna-agents` is listed among related repos
  in CLAUDE.md; and the RM11/RM12 provenance-column comments read "0.4 (from the 0.5 scope)".

## 2026-07-11 — 0.4.0 (unpublished) — round-trip hardening + audit fixes

A correctness/robustness pass over the 0.4 work, before publish. Packages bumped **0.3.0 → 0.4.0**
(the `just-dna-format` / `just-dna-compiler` versions now match the milestone the code already
implements). **`schema_version` stays `"1.0"`.** Still unpublished, so the `artifact.digest` changes
below are free to absorb.

- **Structured per-version authorship (RM14; docs/USE_CASES.md §5a).** A new optional
  `authorship: list[Contribution]` on `module_spec.yaml` (and `ModuleManifest`), unbundling the flat
  `authors: list[str]` + free-form `curator` (which smuggled author-kind via the `"ai-module-creator"`
  default) into three orthogonal axes (P5): `who` (identity), `role` (closed vocab
  `created`/`edited`/`audited`/`reviewed`), and `kind` — an **open, multi-valued** tag set with a
  recommended seed: a human ladder of assurance `human` → `human_expert` → `human_certified`
  (medically/board-certified), or `ai` plus a scale tag `agent`/`team`/`swarm`. There is no `hybrid`
  tag — a joint contribution is two entries (a human and an ai), so the mix is always explicit. The
  motivating case: **AI and human error-spectra overlap but differ**, so a consumer (the network
  validator, a marketplace review queue, a human auditor) routes scrutiny by author-kind — the format
  carries the kind, the consumer picks the profile (north star). It is **manifest metadata, out of
  `artifact.digest`** (like `provenance`/`logs`/`panel`), so it is additive/digest-neutral even
  post-freeze and two versions with identical annotation content but different authorship keep one
  content identity. `authoring_reference()` surfaces the `Contribution` model + `author_role`
  vocabulary + `author_kind` seed automatically. Folding the flat `authors`/`curator` in is a
  1.0-cleanup item.
- **Provenance columns on `StudyRow` (RM11/RM12; docs/USE_CASES.md §4a).** Three optional columns that
  let a *network-first* validator (RM13, a consumer — Principle 2 keeps fetching out of these libs)
  scrutinise a module without the format ever downloading:
  - **`doi`** — Digital Object Identifier, wider than `pmid` (covers preprints/books/datasets with no
    PubMed id); validated against the DOI grammar and kept verbatim.
  - **`provenance_quote`** / **`provenance_regex`** — a keyword phrase and/or regex locating a study's
    claim in the cited article's fulltext, so a validator can confirm fulltext-contains yes/no. The
    regex is a Principle-1 *declarative pattern grammar* (data, not code): compiled at author time for
    a sanity check, matched consumer-side by a linear-time/ReDoS-safe engine. The provenance analogue
    of `source_field`.
  All optional → additive/monotonic (P3/P8); materialized into `studies.parquet` with lossless
  round-trip (P7). The mandatory-`pmid` → doi-first relaxation remains a 1.0-cleanup item (a required
  field can't be demoted in-major). `authoring_reference()` picks the columns up automatically.

- **Round-trip fidelity fixes (CONSTITUTION Principle 7).** Four shapes silently round-tripped wrong
  — the happy path (rsid-keyed, uniform priority, no explicit-`False` booleans) stayed green, so the
  invariant was only nominally tested:
  - **Position-only study rows** (`rsid` null, `chrom`/`start`/`ref` set) were dropped on compile and
    made *recompile fail*; `studies.parquet` now carries the position columns.
  - **Position-only variant annotations** (gene/phenotype/category) were lost because the reverse
    lookup keyed on the null `rsid`; `annotations.parquet` now carries an explicit `variant_key`.
  - **`priority`** was fabricated on reverse (an unset row inherited the mode as an inferred default,
    turning `['high', null]` into `['high', 'high']`); it is now written verbatim.
  - **ClinVar booleans** (`clinvar`/`pathogenic`/`benign`) collapsed an authored `False` to `None`;
    they are now materialized tri-state (nullable), matching the 0.4 axes.
- **Resolver fix.** A position-only-without-`ref` variant never resolved its rsid even on an Ensembl
  hit (the result was keyed by the DB ref, the lookup by `chrom:start:None`) — keys now reconcile.
- **Input hardening.** `start` positions are `ge=0` (a negative position is a clean validation error,
  not a polars `UInt32` overflow); `weight`/`effect_size`/measure bounds/`activity_value`/
  `match_rate_floor` reject non-finite floats (`NaN`/`inf`) that broke round-trip equality.
- **Tests (+20).** New round-trip regressions for every shape above; resolver unit tests over a
  **synthetic** parquet cache (the resolver + cache were previously covered only by
  integration-gated tests that skip in CI); `aggregate_provenance`, continuous-fraction coverage-gap,
  and several untriggered validator/error branches.
- **Docs reconciled with shipped code.** ROADMAP no longer frames 0.4 as unbuilt / PGS as note-only /
  a `VariantRow.copy_number` field that was rejected; READMEs describe composed modules (not a fixed
  three-parquet artifact) and the full dependency lists; the CONSTITUTION dependency-tier goal and
  `CLAUDE.md` acknowledge `cryptography` alongside `pydantic`.

## 2026-07-10 — 0.4 quantitative tables + composed modules

Additive 0.4 schema shapes (frozen per `docs/PROPOSAL_0_4.md`) with full compiler materialization.
**`schema_version` stays `"1.0"`** — every 0.1–0.3 module keeps validating; all new tables/columns
are optional.

- **The measure→phenotype binning primitive** (`just_dna_format.binning`): one shared column
  vocabulary (`measure_kind`, inclusive `[measure_min, measure_max]`, `direction`/`clin_sig`/
  `trait_efo_id`, `conclusion`, mandatory `unresolved` sentinel, declarative `source_field` pointer)
  across per-quantity tables — `activity_phenotype.csv`, `copynumbers.csv` (+ optional
  `modifier_gene`/`modifier_cn`), `repeat_alleles.csv`, `heteroplasmy.csv` (tissue + legacy-`NC_001807`
  reference guard). There is **no `copy_number` column** — a sharp value is `measure_min == measure_max`.
- **PGx star-alleles** (`just_dna_format.pgx`): `haplotypes.csv` (variant↔allele junction),
  `allele_function.csv` (star-string verbatim identity + optional `suballele`/CN/SV conveniences),
  `diplotypes.csv` (canonicalized pair fallback, + optional `drug`/`response`/`evidence_level`), and
  **PharmGKB** `pharm_variants.csv` (single-variant drug response, `evidence_level` 1A…4).
- **PGS** (`just_dna_format.pgs`): `pgs.csv` — a PGS-Catalog-ID manifest with the ancestry-validity
  one-way-door fields (`training_ancestry`, `training_cohort`, `match_rate_floor`, `research_tier`).
- **`VariantRow` general axes** (optional): `requires_callable`, `acmg_sf`, `actionability`
  (validated against `ACTIONABILITY_SEED`) — retired from the reserved namespace.
- **Compiler materialization (RM1 + RM2).** A generic model-driven materializer compiles all nine
  table kinds to parquet with lossless, idempotent round-trip. A module **composes from optional
  table kinds**: `variants.csv` is no longer mandatory — a PGx/PharmGKB/PRS-only module compiles and
  reverses without an empty `variants.csv`; `studies.csv` is required iff `variants.csv` is present.
- **Table-level coherence is enforced at compile time.** `validate_bins` now runs inside
  `validate_spec`: **overlapping resolved bins are a compile error** (a measurement would select two
  phenotypes), interior coverage gaps a warning, and more than one `unresolved` sentinel per key
  group an error. Duplicate rows (diplotype pair, `pgs_id`, `(pharm variant, drug)`, allele-function
  allele, haplotype-defining variant) are errors — the 0.4 analog of the SNP core's duplicate check.
- **Drift-proof authoring reference** (`just_dna_format.reference.authoring_reference()` /
  `json_schemas()`, RM8) generated from the live models, plus a recommended `RECOMMENDED_COLORS`/
  `RECOMMENDED_ICONS` palette (RM9) — so MCP servers / agents render the current field set instead of
  a hand-maintained summary that drifts.
- **Shared vocabulary leaf** (`just_dna_format.vocab`): the orthogonal-axis vocabularies and
  identifier grammars moved out of `spec` into one dependency-light source of truth, re-exported from
  `spec` for backward compatibility.

## 2026-07-08 — just-dna-format 0.3.0 + just-dna-compiler 0.3.0

Additive schema + partial compiler coverage for the 0.3 columns. **`schema_version` stays `"1.0"`** —
every 0.1/0.2 module keeps validating; all new columns are optional. Design captured in
`docs/ROADMAP.md` (Planned for 0.3 / 0.4), invariants in `docs/CONSTITUTION.md`, worked drafts in
`docs/REFERENCE_EXAMPLES.md`, and the compiler coverage split in `docs/COMPILER.md`.

- **New optional columns.** `VariantRow`: `direction` (protective|risk|neutral|unknown),
  `stat_significance` (significant|suggestive|not_significant|unknown), `effect_size` +
  `effect_measure` (open vocab), `effect_allele`, `flags` (open list; reserved:
  conditional|phased|pleiotropic), `trait_efo_id` (EFO/MONDO CURIEs, matches just-prs), `clin_sig`
  (ClinVar/ACMG vocab). `StudyRow`: `stat_significance`, `effect_size`, `effect_measure`,
  `trait_efo_id`.
- **Genotype widened** to accept a single allele (hemizygous X/Y, homoplasmic MT) and a phased `A|G`
  (order-preserved), alongside the existing sorted unphased `A/G`.
- **Compiler — validator complete; derivations, boolean sync, and phase round-trip now ship** (see
  `docs/COMPILER.md`). New columns materialize into `weights.parquet`/`studies.parquet`; non-reserved
  `flags` surface as INFO via the new `ValidationResult.info`; warnings for a two-allele `MT` **or
  `Y`** genotype (X excluded — it is diploid in XX) and a `direction`/`weight` sign mismatch.
- **Upgrade derivation shipped** (`just_dna_format.derive`, `pydantic`-only leaf module). `state`(+
  `weight`) → `direction`/`stat_significance` and the ClinVar booleans ↔ `clin_sig`, exposed as
  non-mutating `VariantRow.effective_*` accessors plus a materializing `VariantRow.upgraded()` and a
  `needs_upgrade` flag — the derivation the marketplace `revalidate`/`needs_upgrade` drift flow
  consumes. `state` and the booleans **stay required/authoritative** (CONSTITUTION Principle 8 — a
  required field is never demoted inside a major); the new axes are optional with these fallbacks.
- **Lossless, idempotent round-trip** (CONSTITUTION Principle 7, now a durable invariant): a `phased`
  bit in `weights.parquet` preserves `A|G` vs sorted `A/G` through `reverse_module` → recompile, and
  compiling the same spec twice yields the same digest. Only *new computed stats* and all of 0.4
  (diplotype/copy-number/PGx star-alleles) remain out of scope.
- **Digest note:** the parquet schema now carries the 0.3 columns + the `phased` bit, so a re-compile
  changes `artifact.digest` for every module (expected on a compiler-version bump; reproducibility
  pinned by `compiler_version`; 0.3 is unpublished, so the change is still free to absorb).
- **Docs:** new root `CLAUDE.md` makes `docs/CONSTITUTION.md` the mandatory first read (discoverability
  gap — the charter was only linked from README/ROADMAP, with no agent entry-point). CONSTITUTION gains
  Principle 7 (round-trip/idempotency) and Principle 8 (requiredness compatibility).
- Tests: `compiler/tests/test_v03.py` (30) + `test_v03_roundtrip.py` (6) + `schema/tests/test_derive.py`
  (13); suite 153 passed / 5 skipped.

## 2026-07-07 — just-dna-format 0.2.0 + just-dna-compiler 0.2.0

First contract release since 0.1.0. **Every change is additive and backwards-compatible**: the
`manifest_version`/`schema_version` stay `"1.0"`, and every 0.1.0 module keeps compiling and
verifying byte-for-byte unchanged (optional fields are absent, optional files never invalidate).
Consumed by just-dna-marketplace 0.5.0.

- **Structured provenance (ROADMAP #1).** New `Provenance` summary on the manifest + `ProvenanceItem`
  / `ProvenanceDoc` models. The compiler auto-discovers `spec_dir/provenance.json` (per-variant
  rationale/verdict/confidence/human-review items), ships + hashes it like a log (kept **out of
  `artifact.digest`**), and records the lean summary (`generator`, `model`, `agent_version`,
  `item_count`, `sha256`) so a catalog can flag "AI-authored · rationale available" without inlining
  text. `verify_manifest(check_provenance=True)` re-hashes it when present.
- **Ed25519 signing (ROADMAP #2 / SPEC §5).** New optional `Signature` block on the manifest, a
  `signing` module (`sign_digest`, `generate_private_key_pem`, `public_key_b64_from_pem`), and
  `integrity.verify_signature`. `verify_manifest(public_key=...)` enforces a pinned key. Signs the
  `artifact.digest` string. Adds a `cryptography` dependency to `just-dna-format`.
- **Cross-version log aggregation (ROADMAP #3).** New `aggregate` module: `aggregate_logs` /
  `aggregate_provenance` return the deduplicated union across a set of version manifests
  ("v3 provenance = v1+v2+v3").
- **ClinVar/quality stats (ROADMAP #5).** `Stats` gains `clinvar_count` / `pathogenic_count` /
  `benign_count`; `validate_spec` and the manifest now summarize the per-row ClinVar flags.
- **PMID validation (ROADMAP #6).** `StudyRow.pmid` now requires at least one extractable PubMed ID
  (bare digits or the legacy `[PMID: N]` / `PMID N; ...` forms) via a re-introduced `PMID_PATTERN` +
  `extract_pmids` helper. The string is kept **verbatim**; a dbSNP URL (no PMID token) is rejected.
  Audited against the Gen-I corpus (all digit-only) so nothing published is invalidated.
- **Gene-panel interface (ROADMAP #7) — interface only, no machinery.** New `GenePanelSpec`
  (`source`, `reference`, `reference_sha256`, `genes`, `significance`), optional on `ModuleSpecConfig`
  and mirrored on the manifest. The compiler records it **verbatim** and does not materialize
  variants from it; the app-level `gene_panel` adapter (just-dna-lite) can now declare its panel
  provenance structurally. Native compile-time materialization is a follow-up gated on a working
  ClinVar reference mixin.
- **Module logo + icon set.** `Display.icon_set` (`fomantic` | `awesome`) selects the no-logo
  fallback glyph's family. New optional `manifest.logo` (`FileEntry`): the compiler discovers
  `spec_dir/logo.{png,jpg,jpeg}`, ships + hashes it, **out of `artifact.digest`** (so a logo swap is
  a PATCH, not a new content identity). `verify_manifest(check_logo=True)` re-hashes when present.
- **`negatives` field (ROADMAP Obs #5).** Optional free-text `VariantRow.negatives` (adverse /
  antagonistic-pleiotropy counterpart to `conclusion`), carried into `weights.parquet` and the
  reverse round-trip.
- **Docs.** `ValidationResult.stats` now documents its de-facto key contract (ROADMAP Obs #1). Item 4
  (resolver provisioning) is unchanged: strictly inject-only, no network.

## 2026-07-07 — just-dna-lite: longevitymap full parity + gene-panel reference implementation

Consumer-side only; no changes to the published packages. Two Gen-I parity advances in just-dna-lite,
flagged here so `-marketplace`/`-agents` see them:

- **longevitymap reached 528/528 rsid parity** (was 518/528). The gap was not Ensembl coverage but a
  genotype-reconstruction bug: heterozygous genotypes were built by concatenating the Ensembl `ref` +
  `alt` columns, and `alt` is a `|`-joined multiallelic list. The fix pairs the module's curated
  effect allele with its single complement and parses two-base `spec` alleles directly. No format API
  change; still compiles under the 0.1.0 contract.
- **Gene-panel reference implementation** for `cardio`/`cancer` (`just_dna_pipelines.v1_port.clinvar`
  + a `gene_panel` adapter): enumerates ClinVar pathogenic/likely-pathogenic variants in the panel's
  gene list into risk-state VariantRows (het + hom-alt), `weight=None`, grounded to the ClinVar
  resource paper (PMID 29165669). Kept within the 0.1.0 contract (multi-base ACGT alleles are legal;
  structural >50 bp and symbolic alleles are dropped). This is the intended upstream reference for a
  native `GenePanelSpec` — see **ROADMAP item 7** (added the same day, with items 8/9 for the APOE
  diplotype and PharmGKB shapes). `pathogenic`/`lnewco`/`drugs` remain deferred.

## 2026-07-06 — just-dna-lite ported the Generation-I OakVar modules onto the DSL

Consumer-side only; no changes to the published packages. just-dna-lite added
`just_dna_pipelines.v1_port` (CLI `pipelines v1-port`), which downloads the Generation-I `just_*`
OakVar postaggregator modules from the `dna-seq` GitHub org, converts their curated SQLite into the
authored DSL (`module_spec.yaml` + `variants.csv` + `studies.csv`), validates and compiles them via
`validate_spec`/`compile_module`, and writes standalone modules to `data/interim/v1_port/`.

- **Curated weights are carried verbatim**; `state` is taken from the source where present and
  otherwise from the weight's sign (reproducing the v1 reporter's `get_color(weight)` behavior).
- **All emitted `pmid` values are digit-only** — see ROADMAP.md → Observations #4 for the PMID audit
  this produced (input to planned item 6; the Gen-I corpus would not be rejected by a bare-digit
  `PMID_PATTERN`).
- Five modules (coronary, thrombophilia, lipidmetabolism, vo2max, longevitymap) compile; the
  reproduced coronary/vo2max/lipidmetabolism rsid sets match the published HF artifacts exactly and
  longevitymap matches 518/528. `superhuman` (URL-only references → no PMIDs) and the non-variant
  modules (cardio/cancer/pathogenic gene panels, drugs/PharmGKB, lnewco APOE diplotype) are
  documented as gaps, not ported. No `just-dna-format` API was exercised beyond the 0.1.0 contract.

## 2026-07-06 — just-dna-pipelines repointed at the published libs

Consumer-side integration in `just-dna-lite/just-dna-pipelines`. No changes to the published
`just-dna-format` / `just-dna-compiler` packages themselves; this entry documents how a consumer
adopted them and the contract facts that surfaced.

### Added
- `just-dna-pipelines` now depends on `just-dna-format>=0.1.0` and `just-dna-compiler>=0.1.0`
  (`uv add`).
- `.json` added to `module_registry._SPEC_SUFFIXES`, so a compiled `manifest.json` is copied
  alongside the parquets on register/install (was previously dropped).

### Changed
- `just_dna_pipelines.module_compiler` is now a **compatibility shim layer** over the libs; the
  duplicated in-repo schema + transform were deleted:
  - `module_compiler/models.py` → re-exports `just_dna_format.spec` (DSL models + constants) and
    `just_dna_compiler.models` (`ValidationResult`, `CompilationResult`).
  - `module_compiler/compiler.py` → re-exports `validate_spec` / `compile_module` /
    `reverse_module` from `just_dna_compiler.compiler`.
  - `module_compiler/resolver.py` → keeps the pipelines-only `ensure_resolver_db` provisioning and
    a `resolve_variants` wrapper that provisions then delegates to `just_dna_compiler.resolver`.
  - `module_compiler/__init__.py`, `cli.py` unchanged in surface (names still resolve via shims).
- Kept pipelines tests were adapted to the libs' current `validate_spec` stats keys — see
  Contract notes below. Test **coverage** is unchanged; only expected key names changed.
- CLI `pipelines module compile` help text updated: it no longer claims to auto-download the
  Ensembl cache from HuggingFace (the lib is inject-only).

### Behavior change (downstream)
- Ensembl resolution is now **inject-only at the library boundary**: `just_dna_compiler` never
  downloads a reference. Provisioning stays in just-dna-pipelines:
  - `register_custom_module` **auto-provisions** — when `resolve_with_ensembl` is on and no cache
    is passed, it calls `ensure_resolver_db()` (idempotent: cheap when the cache exists, builds/
    downloads from HuggingFace only when absent) and injects the result. Failure degrades to
    inject-only (resolution skipped with a warning). This preserves the pre-extraction convenience.
  - Direct callers of `just_dna_pipelines.module_compiler.resolver.resolve_variants` also
    auto-provision via `ensure_resolver_db`.
  - `compile_module` itself (the library re-export) remains inject-only: called directly with no
    cache and none present, it skips resolution with a warning rather than downloading. The
    `pipelines module compile` CLI relies on an already-provisioned cache (help text updated).
  - Integration tests pass because their `ensembl_db_path` fixture provisions the default cache
    the lib then reads.

### Contract notes for other consumers (-marketplace, -agents)
- **`ValidationResult.stats` keys renamed** vs. the pre-extraction schema:
  `unique_genes → gene_count`, `study_rows → study_count`, `unique_variants → variant_count`;
  `genes` / `categories` are sorted lists with `None` filtered out. `unique_rsids` and
  `module_name` are unchanged.
- **`VALID_PRIORITIES` and `PMID_PATTERN` are not in `just_dna_format.spec`** — they were dead code
  in the original schema (no validator referenced them / the PMID validator was commented out). The
  live study rule remains "pmid must be non-empty".

## 2026-07-06 — just-dna-format 0.1.0 + just-dna-compiler 0.1.0 (initial workspace release)

Restructured the format into a uv workspace publishing the two packages, and extracted the schema +
transform out of just-dna-pipelines so they are shared, not duplicated. `manifest_version` /
`schema_version` established at `"1.0"`.

- **`just-dna-format`** (schema; `pydantic` + stdlib at this point): `spec` (the authored DSL —
  `ModuleSpecConfig`, `VariantRow`, `StudyRow`, `ModuleInfo` extending `Display`); `manifest`
  (`ModuleManifest` + `Identity` / `Display` / `Stats` / `Compilation` / `FileEntry` / `Artifact`);
  `integrity` (`sha256_file`, the `artifact_digest` Merkle root, `build_artifact`, `verify_manifest`);
  `identity` (name/namespace rules, SemVer `Version` / `parse_version`, `canonical_id`, legacy
  `vN → N.0.0`).
- **`just-dna-compiler`** (transform; + polars / duckdb / pyyaml / platformdirs / python-dotenv):
  `validate_spec`, `compile_module` (emits `manifest.json` with input + artifact hashes and the
  digest, plus `genes` / `categories` stats), `reverse_module`, and a pipelines-free, **inject-only**
  Ensembl `resolver` (never downloads).
- **Provenance logs.** Optional per-version hashed log files (`ModuleManifest.logs`) — a top-level
  `*.log` plus a `logs/` per-role subtree — copied into the module dir, hashed like `inputs`, kept
  **out of `artifact.digest`**. Absent logs never invalidate; `verify_manifest(check_logs=True)`.
- **Ensembl cache reuse.** `just_dna_compiler.cache` mirrors just-dna-lite's on-disk layout
  (`$JUST_DNA_PIPELINES_CACHE_DIR/ensembl_variations/…`, `.env`-driven); it locates a reference but
  never downloads one.
- Tests: 82 passing (schema + compiler), incl. regression tests ported from just-dna-lite; the
  Ensembl resolver tests are `@integration` (skip without a cache).
