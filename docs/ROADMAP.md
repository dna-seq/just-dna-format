# just-dna-format — Roadmap

This repo (a uv workspace publishing `just-dna-format` + `just-dna-compiler`) is the schema
contract and reference compiler for just-dna annotation modules. This doc tracks what shipped in
**0.1.0** and what's planned for **0.2**.

## Shipped in 0.1.0

- **`just-dna-format`** (schema, pydantic + stdlib): `spec` (authored DSL: `ModuleSpecConfig`,
  `VariantRow`, `StudyRow`, `ModuleInfo` extending `Display`), `manifest` (`ModuleManifest` +
  `Identity`/`Display`/`Stats`/`Compilation`/`FileEntry`/`Artifact`), `integrity` (`sha256_file`,
  `artifact_digest` Merkle root, `build_artifact`, `verify_manifest`), `identity` (name/namespace
  rules, SemVer, `canonical_id`, legacy `vN → N.0.0`).
- **`just-dna-compiler`** (transform, + polars/duckdb/pyyaml/platformdirs/dotenv): `validate_spec`,
  `compile_module` (emits `manifest.json` with input/artifact hashes + digest, `genes`/`categories`
  stats), `reverse_module`, and a pipelines-free Ensembl `resolver`.
- **Provenance logs**: optional per-version hashed log files (`ModuleManifest.logs`) — a top-level
  `*.log` plus a `logs/` per-role subtree — copied into the module dir, hashed like `inputs`, kept
  **out of `artifact.digest`**. Absent logs never invalidate; `verify_manifest(check_logs=True)`.
- **Ensembl cache reuse**: `just_dna_compiler.cache` mirrors just-dna-lite's layout
  (`$JUST_DNA_PIPELINES_CACHE_DIR/ensembl_variations/...`, `.env`-driven); never downloads.
- **Tests**: 82 passing (schema + compiler), incl. regression tests ported from just-dna-lite;
  Ensembl resolver tests are `@integration` (skip without a cache).

## Planned for 0.2 — ✅ shipped in 0.2.0 (2026-07-07)

Items 1, 2, 3, 5, 6 are done; item 4 was decided as-is (no change). See CHANGELOG 2026-07-07
(just-dna-format/compiler 0.2.0). All additive — no `schema_version` bump.

| # | Item | Status |
|---|---|---|
| 1 | **Structured provenance** | ✅ Done. `Provenance` summary on the manifest + `ProvenanceItem`/`ProvenanceDoc`; compiler discovers `provenance.json`, ships + hashes it out of `artifact.digest`, records the summary; `verify_manifest(check_provenance=True)`. |
| 2 | **Ed25519 signing** | ✅ Done. Optional `Signature` block; `signing` module + `integrity.verify_signature`; `verify_manifest(public_key=...)` enforces a pinned key. Signs the `artifact.digest` string. Added `cryptography` dep. |
| 3 | **Cross-version log aggregation helper** | ✅ Done. `aggregate.aggregate_logs` / `aggregate_provenance` return the deduplicated union across version manifests. |
| 4 | **Resolver cache provisioning** | ⏹ Decided: keep the resolver **strictly inject-only** (0.1 stance, no network). No change in 0.2.0. Provisioning stays app-side (just-dna-lite's `ensure_resolver_db`). |
| 5 | **ClinVar/quality flags in stats** | ✅ Done. `Stats.clinvar_count` / `pathogenic_count` / `benign_count`; summarized by `validate_spec` + the manifest. |
| 6 | **Tighten `StudyRow.pmid` validation** | ✅ Done. Re-introduced `PMID_PATTERN` + `extract_pmids`: requires ≥1 extractable PMID (bare digits or legacy `[PMID: N]` / `PMID N; ...`), keeps the string verbatim, rejects dbSNP URLs. Gen-I corpus audited (all digit-only) → nothing published is invalidated. |

### Also shipped in 0.2.0 (beyond the original table)

- **Module logo + icon set.** `Display.icon_set` (`fomantic` | `awesome`) picks the no-logo fallback
  glyph family; new optional `manifest.logo` (compiler discovers `logo.{png,jpg,jpeg}`, hashes it
  **out of `artifact.digest`** so a logo swap is a PATCH). `verify_manifest(check_logo=True)`.
- **`negatives` field (Obs #5).** Optional free-text `VariantRow.negatives`, carried into
  `weights.parquet` and the reverse round-trip.
- **Stats-shape docs (Obs #1).** `ValidationResult.stats` documents its de-facto key contract.

## Gen-I parity: new module shapes needed (raised by just-dna-lite, 2026-07-07)

Porting the Generation-I OakVar modules surfaced **four** modules that the current single-rsid,
per-genotype `VariantRow` schema cannot express faithfully. The six variant-backed modules are now
fully ported (longevitymap reached 528/528 rsids on 2026-07-07 — see CHANGELOG); what remains are
structural gaps, recorded here in full (including deferred ones) so the format owners can schedule
them. None require a `schema_version` bump if added as *new, additive* spec kinds.

| # | Item | Modules | Notes |
|---|---|---|---|
| 7 | **Gene-panel module type** (module = a **gene set** + a **pathogenicity predicate** over a reference, not an enumerated variant table) | `cardio` (~280 genes), `cancer` (~380 genes), `pathogenic` (no gene list — all genes) | Gen-I `just_cardio`/`just_cancer` ship only `data/genes.txt`; at runtime they flagged ClinVar pathogenic/likely-pathogenic variants whose `GENEINFO` gene ∈ the list. `just_pathogenic` had no data at all (flag every pathogenic variant). There is **no per-variant curated genotype/weight/conclusion** to convert — the curation *is* the gene list + the "pathogenic" rule. Proposed shape: a `GenePanelSpec` with `genes: list[str]`, `significance: list[str]` (e.g. `pathogenic`, `likely_pathogenic`), and a reference key (ClinVar or the Ensembl `CLIN_*` columns). Compiler would materialize the matching variants into `weights.parquet` at compile time (state=`risk`, weight=`None`, conclusion from ClinVar `CLNDN`), so the artifact stays a normal variant table but the **authored** spec is tiny and maintainable. Requires: (a) deciding whether the panel resolves against a dedicated ClinVar reference (NCBI `clinvar.vcf.gz`, ~190 MB GRCh38 — just-dna-lite has hauled it to `/data/just-dna-cache/clinvar/`) **or** the existing Ensembl parquets (which already carry `CLIN_pathogenic`/`CLIN_likely_pathogenic` booleans but **no gene symbol**, so a gene→region map would still be needed); (b) a `gene`-column resolver. **Decided (2026-07-07, just-dna-lite owner):** feature-complete home is the format/compiler (a native `GenePanelSpec`), but *for now* an app-level **reference implementation** ships in just-dna-lite (`just_dna_pipelines.v1_port.clinvar` + the `gene_panel` adapter) — it enumerates ClinVar pathogenic/likely-pathogenic variants in the gene set as risk-state rows (het + hom-alt carrier genotypes) and grounds every variant to the ClinVar resource paper (PMID **29165669**, verified). SNVs and small ACGT indels are expressible (genotype alleles are `^[ACGT]+$`, multi-base allowed); symbolic/complex alleles are skipped and counted. That adapter is the intended upstream reference. All three are now built this way (2026-07-07): cardio (123k rows / 304 genes) and cancer (145k / 319) from their gene lists with **gene-symbol reconciliation** against NCBI gene_info (legacy aliases → current symbols; typos reported, not guessed), and `pathogenic` (674k / 5,540 genes) genome-wide with no gene filter. **Update (0.2.0):** the earlier "app-level home for now" call was really about 0.1.0, before just-dna-lite depended on these libs with no code duplication. Now these packages are the truth source, so the FR's two concerns are split cleanly: 0.2.0 ships the **`GenePanelSpec` interface** (`source`, `reference`, `reference_sha256`, `genes`, `significance`) on `ModuleSpecConfig` + the manifest, additive and backwards-compatible — the app-level adapter can now *declare* its panel provenance structurally instead of burying it in free-form `method`. The compiler records the panel **verbatim** and does **not** materialize variants from it (no ClinVar reader / gene→region resolver here). Native compile-time **materialization** (gene set + significance predicate → `weights.parquet`) is the remaining follow-up, gated on a **working ClinVar reference mixin proven app-side in just-dna-lite**; when that lands the compiler gains the machinery and the app-level enumeration retires. |
| 8 | **Multi-locus diplotype / haplotype genotype** | `lnewco` (APOE) | `just_lnewco` keys conclusions on an **APOE diplotype spanning two rsids** — `rs429358` + `rs7412` combine into ε2/ε3/ε4 haplotypes, and the conclusion is on the *pair* (e.g. `ε4/ε4`). `VariantRow.genotype` is a single locus's two alleles and cannot represent a genotype defined across multiple SNPs. Proposed shape: a `HaplotypeRow`/`DiplotypeRow` with an ordered list of `(rsid, allele)` defining a haplotype, a table of named haplotypes (ε2/ε3/ε4), and conclusions keyed on a diplotype (a pair of haplotype names). Star-allele pharmacogenomic loci (CYP2D6 etc.) would reuse the same shape, so this is worth designing generally. Deferred. |
| 9 | **PharmGKB pharmacogenomics fields** | `drugs` | `just_drugs` (`data/annotation_tab.tsv`, PharmGKB) is drug-response annotation — a different domain. A variant maps to a **drug** + a **response/phenotype** + a PharmGKB **evidence level** (1A…4), not a risk weight. Proposed: either extend `VariantRow` with optional `drug`, `response`, `evidence_level` fields, or a sibling `PharmVariantRow`. Also interacts with #8 (many PGx calls are star-allele diplotypes). Largest effort; scope as its own project. Deferred. |

## Non-goals for these packages

To keep the tiers clean, these libraries deliberately **do not** pull Dagster, LLM SDKs, or
HuggingFace, and do not download reference data. Orchestration/AI authoring live in
`just-dna-pipelines`; artifact storage/serving lives in `just-dna-marketplace`.

## Cross-repo follow-ups (tracked elsewhere)

- **just-dna-pipelines** — ✅ **done (2026-07-06)**: depends on `just-dna-format>=0.1.0` +
  `just-dna-compiler>=0.1.0`; `module_compiler` is now re-export shims over the libs (duplicate
  transform/schema deleted, `ensure_resolver_db` provisioning kept); `.json` added to
  `_SPEC_SUFFIXES`. See CHANGELOG.md 2026-07-06.
- **just-dna-marketplace** — add `just-dna-compiler` as the M4 publish dependency; serve `logs` via
  the files endpoint; aggregate cross-version provenance for the module detail view.

## Observations from the just-dna-lite integration (2026-07-06)

Surfaced while repointing just-dna-pipelines at the libs — flagged here so `-marketplace` and
`-agents` don't rediscover them:

1. **`validate_spec` stats keys were renamed** vs. the pre-extraction schema and are a de-facto
   contract: `unique_genes → gene_count`, `study_rows → study_count`, `unique_variants →
   variant_count`; `genes`/`categories` are now sorted lists filtering `None`. `unique_rsids` and
   `module_name` are unchanged. Any consumer that asserted on the old keys must update (just-dna-lite
   tests already did). Consider documenting the `stats` shape explicitly on `ValidationResult`.
2. **`VALID_PRIORITIES` and `PMID_PATTERN` were intentionally not carried into `just_dna_format.spec`.**
   Confirmed dead in the original schema: `VALID_PRIORITIES` was referenced by no validator (priority
   is free-form `Optional[str]`), and `PMID_PATTERN`'s validator was commented out (the live rule is
   only "pmid non-empty", which the lib preserves). Tightening PMID validation is planned as a 0.2
   item (see table row 6); it stays as-is for 0.1. Stricter priority validation would likewise be a
   new opt-in validator, not a restoration.
3. **Ensembl provisioning is not in the libs by design** (inject-only, ROADMAP item 4). just-dna-lite
   keeps `ensure_resolver_db` (HF download + DuckDB build) in `module_compiler/resolver.py` and injects
   the cache. `register_custom_module` and direct `resolve_variants` callers auto-provision via
   `ensure_resolver_db` (idempotent), preserving the pre-extraction convenience. The bare
   `compile_module` re-export and the `pipelines module compile` CLI stay inject-only: with no cache
   present they skip resolution with a warning rather than downloading.
4. **PMID audit (item 6 input) from the Gen-I module port (2026-07-06).** just-dna-lite ported the
   six variant-backed Generation-I OakVar modules (`dna-seq` org `just_*` repos) into the DSL
   (`just_dna_pipelines.v1_port`). Their PubMed references come in three forms: clean integers
   (`studies.pubmed_id` in thrombophilia/lipidmetabolism), prefixed/bracketed lists
   (`PMID 17478681; PMID: 30278588` in coronary/vo2max; `[PMID 28373160]` in the rsids tables), and
   bare numbers (`quickpubmed` in longevitymap). All are trivially reducible to **digit-only** PMIDs;
   the ported modules already emit digit-only `pmid` values and validate. This suggests a 0.2
   `PMID_PATTERN` accepting bare digits (with a normalization/extraction step for the legacy
   bracketed form) would **not** reject the Gen-I corpus. The only genuinely non-conforming source is
   `just_superhuman`, whose `references` are dbSNP URLs, not PMIDs — it produces zero grounded studies
   regardless of the pattern, so it's an evidence gap, not a validation-strictness question.

5. **Proposed: a first-class "negatives / pleiotropy" field on `VariantRow`.** (Surfaced during the
   `superhuman` v2 curation, 2026-07-07.) Protective-allele modules routinely carry an *adverse /
   antagonistic-pleiotropy* counterpart to the beneficial effect, and the curators treat it as a
   distinct, load-bearing piece of the annotation — e.g. the Church-lab AREP "Protective Alleles"
   page has an explicit **"Potential Negatives"** column (APOL1 G1/G2 → kidney-disease risk; CCR5
   Δ32 → West Nile / flu susceptibility; COMT V158M → "ADHD, headaches"; HBB HbS → exertional
   rhabdomyolysis; PCSK9 LOF → diabetes / low cognition). The Gen-I `just_superhuman` SQLite mirrors
   this with an `adverse_effects` column. Today just-dna-lite has nowhere structured to put it, so the
   port **concatenates it into `conclusion`** (`"<benefit>. Adverse effects: <negatives>"`), which
   works but is unstructured — a UI can't render "benefit vs. trade-off" distinctly, and it can't be
   queried/filtered. Proposal: an optional free-text `negatives` (or `pleiotropy` / `adverse`) field
   on `VariantRow` + `weights.parquet`, parallel to `conclusion`. Free-text (like `conclusion`), not
   an enum — the trade-offs are heterogeneous. Consumers ignore it if absent (backward-compatible).
   This respects the curator's "author's vision" framing (benefit *and* stated caveat) as first-class
   data rather than prose. If adopted, the superhuman adapter would move `adverse_effects` / AREP
   "Potential Negatives" out of `conclusion` and into the new field.
