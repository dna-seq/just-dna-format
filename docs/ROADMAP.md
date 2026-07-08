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

## Planned for 0.3

**Design converged 2026-07-08; not built yet — this section is the exact brief for the next format
run.** Everything here is **additive** — no `schema_version` bump (stays `"1.0"`), existing 0.1/0.2
modules keep validating, and the new columns are back-populated from the old `state` field by the
upgrade derivation below, fed into the marketplace `revalidate` / `needs_upgrade` contract-drift
flow (which shipped in marketplace 0.5 — the format supplies the derivation function; the flow that
flags drifted-but-fixable modules already exists).

0.3 untangles the overloaded `state` field into **orthogonal axes** and replaces the lossy ClinVar
booleans with a proper `clin_sig` tier — all **additive columns on the existing `variants.csv` /
`studies.csv`**, plus the `genotype` widening (5b). It adds **no new file kinds and no consumer
gate**, so it ships cleanly on its own. The **relational shapes (diplotypes, copy-number) and the
PGx star-allele model are rescoped to 0.4** (see *Planned for 0.4* below) — a detailed plan to be
vetted. Follows the existing `frozenset[str]` + validator idiom — **no `Enum`/`Literal`** (the schema
has none). **Simple SNV modules need none of the 0.4 layer** — the columns here are all optional.

**One-way-door discipline.** Because backward-compat makes these column names and vocabularies
*permanent*, the design was audited against the near-certain future additions (full ClinVar/ACMG,
PGS modules, VEP `consequence`/`impact`/frequency, PharmGKB) to avoid collisions, duplications, and
later retirements. The key outcome: the bare word `significance` is **already taken** for the
*clinical* axis (`GenePanelSpec.significance` = `['pathogenic','likely_pathogenic']`; `p_value` is
already "Statistical significance"), so the statistical axis is named **`stat_significance`** and the
clinical tier gets its own **`clin_sig`** column. See *Reserved namespace* and *Guardrails* below.

Scoping note: the `state`-split alone (item 1) is just additive columns — a **0.2.1 patch** that can
ship on its own. **0.3 = items 1–6 + 5b + the upgrade derivation** (additive columns on the existing
CSVs). **0.4 = the relational shapes (items 7, 7b) + PGx star-alleles + PharmGKB** — new file kinds,
consumer-gated, a detailed plan to be vetted with grounding to come. Item 8 (PGS) stays note-only.
Worked drafts for all of these live in [REFERENCE_EXAMPLES.md](REFERENCE_EXAMPLES.md).

### 0.3 feasibility & sequencing (dogfooded against the repo)

Grounded in the actual packages: schema deps = `pydantic`+`cryptography`; compiler deps =
`polars`/`duckdb`/`pyyaml`/`platformdirs`/`dotenv`; **no Eliot anywhere** (only stdlib `logging` in
`resolver.py`); `ValidationResult` exposes `errors`/`warnings` only; genotype is parsed with
`genotype.split("/")` (compiler.py:508); the artifact is a fixed `_OUTPUT_FILES` tuple of three
parquets (compiler.py:41).

- **Buildable now, self-contained (schema + compiler, additive):** items 1, 2, 3, 5, 5b, 6 and the
  upgrade derivation — new optional columns + validators + a `state→…` derivation function; the
  marketplace `revalidate`/`needs_upgrade` flow that consumes it shipped in 0.5. Item 5b needs a
  one-line compiler change (widen `split("/")` to accept a single allele and `|`).
- **Buildable but re-specced:** item 4 `flags` columns are trivial, but the unknown-tag **INFO must
  not use Eliot** (not a dependency here) — surface it via a new additive `ValidationResult.info`
  list or stdlib `logging`, not the marketplace's Eliot convention.
- **Rescoped to 0.4 (new file kinds, consumer-gated):** item 7 diplotype/haplotype and item 7b
  copy-number dosage, plus the PGx star-allele model. The format *can* define the models, compile the
  new CSVs, and add `haplotypes.parquet`/`diplotypes.parquet`/`copynumbers.parquet`/etc. to
  `_OUTPUT_FILES` (additive — only modules shipping them change digest), but they deliver nothing
  until a consumer does diplotype *calling* + phased-VCF parsing / **CNV calling** (just-dna-lite).
  See *Planned for 0.4* below — a detailed plan to be vetted with maintainer-provided grounding.

**Concrete 0.3 change list (columns only — the shippable core):**
- *Schema pkg (`spec.py`):* add optional `direction`, `stat_significance`, `effect_size`,
  `effect_measure`, `flags`, `effect_allele`, `trait_efo_id`, `clin_sig` (+
  `StudyRow.stat_significance`/`effect_size`/`effect_measure`/`trait_efo_id`); new `frozenset`
  vocabularies + validators; **widen the `genotype` validator** (single allele + `\|`, item 5b); make
  `state` and `pathogenic`/`benign` derived aliases; relax `VALID_STATES` reads. (The new relational
  models — `HaplotypeRow`/`DiplotypeRow`/`CopyNumberRow`/allele-function — and `copy_number` are
  **0.4**.)
- *Compiler pkg (`compiler.py`):* widen `genotype.split("/")` → handle `\|` and single alleles
  (`:508` + the reverse join `:731`); carry the new columns into `weights.parquet`; emit the
  unknown-flag **INFO** via a new additive `ValidationResult.info` list or stdlib `logging` (**not**
  Eliot); **warn** on a two-allele genotype at `MT`/hemizygous loci. (New CSV kinds + parquet outputs
  are **0.4**.)
- *Cross-repo:* the `state→direction/stat_significance` derivation feeds the marketplace
  `revalidate`/`needs_upgrade` flow (shipped in marketplace 0.5).
- **Blocked / not 0.3-feasible:**
  - **Gene-panel materialization (Gen-I item 7):** needs an *injected* ClinVar reference (~190 MB) +
    a gene→region resolver the libs lack; compile-time fetching is barred by Constitution P2
    (no network). Gated on the app-side ClinVar mixin. Only the 0.2.0 `GenePanelSpec` *interface* ships.
  - **PGS (item 8):** no consumer contract — just-prs has no "PGS collection" object and scores IDs
    independently, so pinning `pgs.csv` now risks the wrong permanent shape. Correctly note-only.
  - **PharmGKB (Gen-I item 9):** its own project — and the natural home for G6PD-style drug-response
    (a "deficiency status" module fits 0.3; the drug-trigger semantics wait on item 9).
  - **Reserved ploidy/non-SNV (MT heteroplasmy, CNV, repeats) and VEP `consequence`/`impact`:**
    reserved namespace only; deliberately not built.

### New / changed columns

| # | Item | Design |
|---|---|---|
| 1 | **Split `state` → `direction` + `stat_significance`** | `direction: Optional[str]` on `VariantRow`, vocab `{protective, risk, neutral, unknown}` — three values are the legacy words verbatim (zero migration), `unknown` is the honest default the old enum lacked. Keep `neutral` (not `benign`) to match legacy and avoid colliding with the existing `benign` ClinVar boolean. `state` becomes a **derived, deprecated back-compat alias**, projecting `direction` into the trimmed legacy set `{protective, risk, neutral}` (`unknown→neutral`); `significant` moves to `stat_significance`, `alt`/`ref` are retired (recoverable from `ref`/`alts`/`genotype`). Read still accepts all six values for compat; only re-published/upgraded modules emit the trimmed set. Rationale in **Observations #6**. |
| 2 | **Graduated `stat_significance` — on BOTH rows** | `VariantRow.stat_significance` (curator's rolled-up judgment) **and** `StudyRow.stat_significance` (per-study call, next to the raw `p_value`), vocab `{significant, suggestive, not_significant, unknown}` — so a consumer distinguishes "not significant" from "unstated". `p_value` stays `str` (no retype). VariantRow = summary a report renders; StudyRow = auditable per-PMID evidence, so pleiotropy falls out as multiple study rows. |
| 3 | **Effect size — on BOTH rows** | `StudyRow.effect_size: Optional[float]` + `effect_measure: Optional[str]`, plus a rolled-up `VariantRow.effect_size`/`effect_measure`. `effect_measure` vocab **aligned to PGS Catalog `weight_type`** (`beta, OR, HR, RR`, log forms, `NR`) and kept permissive, so PGS and variant modules share one measure vocabulary. Significance (is it real?) and magnitude (how big?) are separate axes; `VariantRow.weight` stays a **module-local score**, *not* a published effect size — document so consumers don't conflate them. |
| 4 | **`flags` — reserved-semantic + open** | Optional multi-valued `VariantRow.flags: list[str]`. Reserved core the tooling acts on: `conditional` (conclusion depends on another locus → the diplotype table), `phased` (valid only on phased data), `pleiotropic` (multi-trait / direction varies). Arbitrary free tags pass through; **unknown tags are surfaced as INFO, never a warning/error** (an open list has nothing to warn about) — via a new additive `ValidationResult.info` list or stdlib `logging.info`, **not** Eliot (the format packages don't depend on it; that's a marketplace convention that doesn't hold here). Do **not** put direction words in flags — `pleiotropic` is a flag, not a `direction` value (the opposing arm stays in `negatives` prose or a per-trait study row). Clinical significance / molecular consequence / drug response must **not** be flags — they get typed columns (see *Reserved namespace*); the INFO event surfaces authors drifting into that anti-pattern. |
| 5 | **`effect_allele` + `trait_efo_id`** | `VariantRow.effect_allele: Optional[str]` — which allele `direction`/`weight`/`effect_size` refer to (today only implied by `ref`/`alts` + `weight` sign — effect-allele/strand confusion is the #1 silent bug here). Matches PGS Catalog's `effect_allele` name; document the strand/build assumption (`+` strand, `genome_build` from `ModuleSpecConfig`). Plus `trait_efo_id: Optional[str]` on `VariantRow` (and `StudyRow`), **copied verbatim from just-prs** (`ScoreInfo.trait_efo_id`, "EFO/MONDO/OBA/HP trait ontology ID(s)") — keeping free-text `phenotype` as the label. Same field name ⇒ variant modules and future PGS modules **join on `trait_efo_id`** with zero glue. |
| 5b | **Widen `genotype`: hemizygous + phased** | The `genotype` validator today hard-codes a **diploid** locus: exactly two `/`-separated `^[ACGT]+$` alleles, `\|` forbidden (`spec.py:157-173`). That cannot express a **hemizygous** call — non-PAR X/Y in males is a single copy, so `A/A` is a semantic lie (2 copies, not 1). Widen the validator to *also* accept (a) a **single allele** (`A`) for hemizygous loci, and (b) the **phased** form `A\|G` (which item 7 needs). **Additive**: widening acceptance never invalidates existing two-allele rows, and the artifact already stores `genotype` as `List[str]` in `weights.parquet` — so this fits a 0.x. Caveat: consumers that *assume* exactly two alleles rely on today's shape, so the widened forms are opt-in and documented. Ploidy *application* (which loci are hemizygous for this sample — sex, karyotype) stays a **consumer** concern; the format only makes the hemizygous call *representable*. Validated by the G6PD dogfood: the author enumerates *both* cardinalities at an X-linked locus (a single-allele hemizygous row **plus** the diploid `T/T`/`C/T`/`C/C` rows), and the consumer matches the sample's actual allele count. Two refinements the dogfood forced: (a) the single-allele genotype *is* the hemizygous signal on chrom X/Y, so the reserved `hemizygous` **flag is redundant** — drop it; (b) widen the compiler's `genotype.split("/")` (compiler.py:508) to handle `\|` and single alleles. Guardrail: **warn on a two-allele genotype at an `MT` (or non-PAR X/Y) locus** — the accepted-chromosome trap. See *Non-diploid & non-SNV loci* below. |
| 6 | **`clin_sig` — clinical tier, aliasing the lossy booleans** | New `VariantRow.clin_sig: Optional[str]` (VEP's exact field name), vocab `{pathogenic, likely_pathogenic, uncertain_significance, likely_benign, benign, drug_response, association, risk_factor, protective, affects, conflicting, not_provided, other}`. The lossy `pathogenic`/`benign` booleans become **derived aliases** (`clin_sig∈{pathogenic,likely_pathogenic}⇒pathogenic=True`; `{benign,likely_benign}⇒benign=True`) — booleans can't express `likely_*`/`uncertain`, and doing it now avoids a second migration. `clinvar` stays a **provenance** boolean ("is it *in* ClinVar?"), orthogonal to the tier. Align `GenePanelSpec.significance` to this exact vocab so the two spellings never diverge. Distinct from `direction` (ClinVar's `protective`/`risk_factor` decompose *out* to `direction`) and `stat_significance`: three axes, three columns. |

## Planned for 0.4 — relational shapes & PGx (detailed plan; grounding to come, to be vetted)

**Expectation (write-down).** The items below are **rescoped from 0.3 to 0.4**. They are a
*spec-led* design: the spec deliberately runs **ahead of implementation** (a proper state of things —
consumer gates are expected, not blockers). The maintainer will **provide grounding** (real
star-allele / diplotype / CNV datasets and consumer needs) to push these forward; 0.4 is then a
**detailed plan to be vetted**, not a build-on-sight.

Affirmed design calls: (1) **keeping this table-modular is correct** — lookup tables, not a new row
type per exception; (2) **star-strings as the canonical allele-unit identity** are the natural choice
(mirrors PharmVar, which itself has no structured SV/CN field); (3) **simple SNV modules never touch
this layer** — everything here is opt-in, and a plain `variants.csv` module ignores it entirely.
Worked drafts: [REFERENCE_EXAMPLES.md](REFERENCE_EXAMPLES.md).

### New relational shapes

- **Item 7 — Diplotype / haplotype (two new lookup-table CSVs; design captured, not built).**
  `haplotypes.csv` = `haplotype_name, rsid, allele` (a haplotype is its set of defining *cis*
  alleles: APOE ε4 = {rs429358:C, rs7412:C}).
  `diplotypes.csv` = `haplotype_a, haplotype_b, trait_efo_id, phenotype, direction,
  stat_significance, effect_size, effect_measure, flags, conclusion, negatives, …` — the same axis
  columns as a variant row. **Key = `(haplotype_a, haplotype_b, trait_efo_id)`, multiple rows per
  pair** (validated by the APOE thought experiment: ε2/ε2 is *protective* for Alzheimer's and *risk*
  for type III hyperlipoproteinemia — keying on the pair alone makes pleiotropy inexpressible; this
  mirrors StudyRow multiplicity for *variant* pleiotropy). The pair is **unordered — canonicalize to
  `haplotype_a <= haplotype_b`**, the same discipline as the alphabetically-sorted `genotype`.
  Because a haplotype *is* a cis allele-set, this machinery **is** phased-genome support: the format
  only *defines* haplotypes; a consumer's generic diplotype caller enumerates pairs of defined
  haplotypes matching the observed genotype — **no author-supplied disambiguation logic** (Constitution
  P1). When >1 pair matches (e.g. APOE ε4/ε2 vs ε1/ε3), the call is ambiguous and the reserved
  `phased` flag marks rows only trustworthy on phased data (`A|G` — see item 5b for the widened
  genotype). Short-term bridge: `flags=[conditional]` on ordinary rows expresses a diplotype-dependent
  conclusion without the new tables (degrades honestly — a single-SNP APOE row can't yield the ε-call,
  and `conditional` says so). Model on PharmGKB/CPIC allele-definition + diplotype-phenotype prior art
  (just-prs's scoring schema already carries `is_haplotype`/`is_diplotype`). Supersedes the two-track
  sketch in deferred item 8 below. **Copy-number star-alleles are out of this shape** — CYP2D6
  `*1xN`/`*5` attach a copy number to an SNV-defined haplotype, which needs copy-number-aware
  *haplotypes* (a heavier follow-up), not the fixed pair here. Simple copy-number *dosage* has its
  own shape in item 7b.

- **Item 7b — Copy-number dosage (`copynumbers.csv`; promoted into 0.3, answering "why not cover CNV
  now?").** For loci whose conclusion is a function of **copy number alone** — SMN1 SMA (0 = affected,
  1 = carrier, 2 = normal, 3+ = normal) — the row has *no rsid, no genotype, no ref/alt*; it is
  `gene, copy_number, direction, stat_significance, clin_sig, phenotype, trait_efo_id, conclusion`.
  So it does **not** fit `VariantRow` (which requires an identifier + a genotype) — it is a **new
  lookup-table CSV**, the same additive pattern as item 7 (add `copynumbers.parquet` to
  `_OUTPUT_FILES`). Also add an optional `VariantRow.copy_number: Optional[int]` for the rarer case
  where a specific variant carries a dosage context. **Why this only *partly* answers "cover #7 with
  0.3":** (1) exactly like item 7, it is **inert until a consumer calls CNVs** from the input and
  matches them — a curator can author the table now, but nothing resolves against it until
  just-dna-lite gains CNV calling (the same consumer gate that deferred the diplotype *build*);
  (2) it covers *simple dosage* but **not** CYP2D6-style CN *star-alleles* (copy number on a
  haplotype), which stay in item 7's deferred scope. Net: 0.3 pins the CN *shape*; a *working* CNV
  feature still waits on the consumer. **SMN1-class vs CYP2D6-class:** item 7b is for whole-gene
  dosage with *no allele identity* (SMN1 SMA — just count functional copies); dosage of a *specific
  phased star-allele* (CYP2D6) is a different beast — see *PGx star-alleles & copy number* below.

- **Item 8 — PGS (note only; no columns pinned this run).** A curated PGS module is **a manifest of
  PGS Catalog IDs, not authored weights** — just-prs resolves `PGSxxxxxx` → a harmonized scoring
  file itself and has **no combine-into-one-score primitive** (`compute_prs_batch` scores each ID
  independently), so per-PGS relative weights would be dead data. Eventual MVP shape `pgs.csv` =
  `pgs_id, trait_efo_id, note, group` + an optional header quality-floor — reusing the **same
  `trait_efo_id`** (item 5) so PGS and variant modules join on trait, and mirroring just-prs's own
  `demo-trait-filter.json` (trait-ID OR-set + `quality_floor`). The authored-weights path (a full
  `effect_allele`+`effect_weight` scoring file matching just-prs `SCORING_FILE_SCHEMA`) is the
  heavier, separable follow-up. Design in the next format run; recorded here so the shape isn't
  forced prematurely.

### PGx star-alleles & copy number — full design picture (spec-led; build deferred, consumer-gated)

Captured now (verified against PharmVar 6.2, CPIC, and the Stargazer/PyPGx/Aldy output schemas) so
the eventual build doesn't get re-architected. This **unifies format items 7 (diplotype), 7b
(copy-number), and 9 (PharmGKB)** into one model; APOE (item 7) is its degenerate, SV-free case.

**Verdict on "one-to-many vs many-to-many":** you need *both*, and the atomic identity is a phased
**allele-unit**, not a bare SNV haplotype. Four tables:

1. **Allele definition — variant ↔ allele is many-to-many** → a junction table (our `haplotypes.csv`
   already is one). One allele = many variants; one variant recurs across many alleles (CYP2D6
   rs1065852 is core-defining in 22 star alleles). PharmVar's own table is 9 columns
   (`Haplotype Name, Gene, rsID, ReferenceSequence, Variant Start/Stop, Reference/Variant Allele,
   Type∈{substitution,insertion,deletion}`), one row per (allele × variant); the **core** allele is
   the function-changing variants shared by all suballeles (`*4` = one row; `*4.001` = ~17).
2. **Allele-unit → activity value** — one-to-many (`*1,*2`=1.0; `*9,*17,*41`=0.5; `*10`=0.25;
   `*3,*4,*5`=0; duplications >1).
3. **Activity score → phenotype** — one-to-many threshold binning, stored **per gene as data, never
   hardcoded** (CYP2D6: PM=0, IM=0.25–1, NM=1.25–2.25, UM=>2.25 — and note these moved by *expert
   consensus* in 2019, e.g. AS=1 went NM→IM, so they must be editable data).
4. **Diplotype → phenotype — many-to-many, and unavoidable** as the *safe canonical form* for the
   structural/duplication/unphased cases (this is why CPIC ships a thousands-of-rows table).

**Why the clean activity-sum decomposition is not sufficient alone** (the cases that force #4 and the
allele-unit concept):
- **Copy number is a property of a specific *cis allele*, not a diplotype-level weight.** `*2×2/*4`
  (AS 2 → NM) vs `*2/*4×2` (AS 1 → IM): same variants, same total CN, different phenotype. A consumer
  that multiplies by *total* CN cannot get this right.
- **Tandems/hybrids are one cis allele-unit in one diplotype slot** — `*36+*10`, `*68+*4`, `*13+*2`
  must be enumerated as first-class allele-unit rows, not decomposed into two slots.
- **Unphased input → a *set* of candidate diplotypes**, not one; the format does not resolve phase
  (consumer does — from `A|G`, item 5b).

**Design consequences for the format:**
- The **star-string is the canonical allele-unit identity, stored verbatim** (`*4`, `*1×2`,
  `*36+*10`) — PharmVar itself has **no structured SV/CN field** (SVs live in the name + a prose doc),
  so we mirror that: `sv_type` / `copy_number` / `hybrid_orientation` are *optional parsed
  conveniences*, and the string is truth. Copy number and cis-tandem structure are **attributes of
  the allele-unit**, never of the diplotype.
- Tables map to CSVs: `haplotypes.csv` (junction, extend `Type` to admit indels; SV alleles are
  defined by *name*, not a variant set), a new `allele_function.csv` (allele-unit → activity value +
  function category), a per-gene `activity_phenotype.csv` (score range → metabolizer phenotype), and
  the `diplotypes.csv` canonical table (item 7) as the fallback. Drug/response/`evidence_level` come
  from **item 9 (PharmGKB)** — the same rows gain those columns.
- **Consumer contract** (a star-allele caller — Stargazer `dip_score`/`phenotype`/`hap*_sv`; PyPGx
  `Genotype`/`Phenotype`/`CNV`/`AlternativePhase`; Aldy `Major`/`Minor`/`Copy`): our tables must be
  consumable by such a caller, which supplies the phased diplotype + CN/SV calls. This is the gate —
  and per the standing decision, an expected, proper gate.

## Cross-cutting design notes (apply to 0.3 and 0.4)

### Rejected: code/DSL in columns (e.g. Lua) — but declarative grammars are welcome

Turing-complete code in cells is rejected — a durable invariant, so its full rationale lives in
[`CONSTITUTION.md`](CONSTITUTION.md) (Principle 1). Lookup tables are the powerful-declarative answer.
Two **declarative** escape hatches are sanctioned if a table is ever outgrown (neither needed yet):
a non-Turing-complete **boolean predicate** (`rs429358==C AND rs7412==C`), and a **pattern grammar
(regex)** for matching allele/star-strings or genotypes — a regex is declarative data, not code,
provided a linear-time/safe engine is used. The line is Turing-completeness + side effects, never
general code. (This is where the PGx star-string matching in 0.4 could lean, if tables prove clumsy.)

### Upgrade derivation (cross-cutting)

Keep existing 0.1/0.2 rows as-is (compat); back-populate the new columns by deriving from `state`,
then flag drifted-but-fixable modules for re-publish as a new PATCH via the marketplace
`revalidate`/`needs_upgrade` flow (the mechanism used for the 0.2.0 PMID tightening).

| old `state` | → `direction` | → `stat_significance` | derived alias `state` |
|---|---|---|---|
| `protective` | protective | unknown | protective |
| `risk` | risk | unknown | risk |
| `neutral` | neutral | unknown | neutral |
| `significant` | unknown *(or from `weight` sign)* | significant | neutral |
| `alt` / `ref` | unknown | unknown | neutral |

Clinical booleans back-populate independently: `pathogenic=True → clin_sig=pathogenic`;
`benign=True → clin_sig=benign`; `clinvar=True` with neither → `uncertain_significance`; otherwise
`clin_sig=None`. Lossy (legacy can't recover `likely_*`), which is acceptable for old data.

### Reserved namespace (do NOT claim these in 0.3/0.4; never encode them as `flags`)

- **`consequence`** — VEP molecular consequence (Sequence-Ontology term, e.g. `missense_variant`).
  Distinct axis from `direction` (phenotypic) and `clin_sig` (clinical). **Never repurpose the bare
  word `effect`** for it.
- **`impact`** — VEP impact `{HIGH, MODERATE, LOW, MODIFIER}`, derived from `consequence`.
- **`allele_frequency`** (+ `af_population`) — gnomAD-style MAF context.
- **PharmGKB (item 9): `drug`, `response`, `evidence_level`** (`1A…4`) — note `evidence_level` is a
  *third* level/significance-flavoured axis distinct from `stat_significance` and `clin_sig`, which
  is exactly why all three need explicit, non-generic names.
- **Ploidy / non-SNV genotype (non-diploid loci — see next section):** `allele_fraction` /
  `heteroplasmy` (float 0–1, for MT and mosaicism), `repeat_count` + `repeat_unit` (STR expansions —
  HTT/FMR1/C9orf72), `zygosity`
  (`{heterozygous, homozygous, hemizygous}`). Reserved flags: `heteroplasmic`, `mitochondrial`,
  `repeat_expansion`, `structural` — **not** `hemizygous` (the G6PD dogfood showed a single-allele
  genotype already conveys it, so the flag would duplicate `(chrom, allele-count)`). Reserve now so
  the names survive the one-way door even though only the hemizygous slice ships in 0.3 (item 5b).

### Non-diploid & non-SNV loci (recognised gap)

0.3's genotype model is **diploid + short-ACGT-sequence** by construction. Item 5b widens it for the
one cheap, high-frequency case — **hemizygous** X/Y. The rest are recognised gaps with a *reserved*
home, deliberately not built in 0.3:

- **Mitochondrial** — **homoplasmic** MT variants *are* reachable in 0.3 via item 5b's single-allele
  genotype (the MT dogfood confirmed `genotype = "G"` for a homoplasmic call). **Heteroplasmy** is
  not — a mutant *fraction* is an `allele_fraction` (float 0–1) + a penetrance threshold, both
  deferred. `MT` is *already* in `VALID_CHROMOSOMES`, so a two-allele MT genotype (fake diploid) is a
  latent trap → the item-5b guardrail warns on it.
- **CNV / gene dosage** — copy number ≠ 2 (SMN1; CYP2D6 duplications/deletions). **Simple dosage**
  (SMN1) now has a 0.3 home — the `copynumbers.csv` shape + optional `VariantRow.copy_number` (item
  7b) — but it stays **inert until a consumer calls CNVs**. **CYP2D6-style CN star-alleles** (copy
  number on a haplotype) need copy-number-aware haplotypes and remain in item 7's deferred scope.
- **Repeat expansions** — the "genotype" is a `repeat_count`, pathogenic above a threshold; a sequence
  regex can't express "42 CAG".

All of the above are reachable **additively** later (widening acceptance / new optional columns), so
no 1.0 break is required to add them — provided the names above stay reserved.

### Guardrails

- **`flags` stays a thin reserved set** + open tags; clinical/consequence/drug get typed columns, so
  they must not be smuggled into `flags` (that duplicates an axis and forces a later retirement). The
  unknown-tag INFO event is the drift signal.
- **No value retirements beyond `state`** (only its `significant`/`alt`/`ref`); every other column is
  purely additive with an `unknown` default, so no existing data is invalidated.
- **No type changes** — `p_value` stays `str`; `stat_significance` is its categorical companion.

The `state` alias, the `alt`/`ref` values, and the `pathogenic`/`benign` booleans-turned-aliases are
all logged as **1.0-cleanup candidates** (see *The 1.0 cleanup* below); the policy itself is
[`CONSTITUTION.md`](CONSTITUTION.md) Principle 3. 0.3 keeps them working; the major bump is
where they retire.

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
| 9 | **PharmGKB pharmacogenomics fields** | `drugs` | `just_drugs` (`data/annotation_tab.tsv`, PharmGKB) is drug-response annotation — a different domain. A variant maps to a **drug** + a **response/phenotype** + a PharmGKB **evidence level** (1A…4), not a risk weight. Proposed: either extend `VariantRow` with optional `drug`, `response`, `evidence_level` fields, or a sibling `PharmVariantRow`. Also interacts with #8 (many PGx calls are star-allele diplotypes). Largest effort; scope as its own project. Deferred. **Now unified** with items 7/7b under *PGx star-alleles & copy number* in the 0.3 section: `drug`/`response`/`evidence_level` are columns added to the same allele-function/diplotype tables. |

## Non-goals for these packages

The goals and non-goals (dependency-light tiers, no network, declarative-not-code) are durable
invariants declared in [`CONSTITUTION.md`](CONSTITUTION.md), not roadmap items. In short: these
libraries never pull Dagster/LLM SDKs/HuggingFace and never download reference data — orchestration
lives in `just-dna-pipelines`, storage/serving in `just-dna-marketplace`.

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

6. **Proposed: split `VariantRow.state` into two orthogonal fields — significance vs. effect
   direction.** (Surfaced during the `superhuman` report work, 2026-07-07.) Today
   `VALID_STATES = {significant, protective, alt, risk, neutral, ref}` mixes two independent axes
   into one field: **statistical significance** (`significant`) and **effect direction**
   (`protective` / `risk` / benign-neutral). A variant can be any combination — significant +
   protective, *insignificant* + protective, significant + benign, significant + pathogenic — but a
   single enum can't represent the cross product, so a curator must drop one axis to record the
   other (e.g. `superhuman` had to choose `significant` **or** `protective`; we now store
   `protective` because the report needs the direction to colour beneficial variants green, losing
   the significance flag). Proposal: two optional fields, e.g. `direction`
   (`protective|risk|benign|unknown`) and `significance` (`significant|not_significant|unknown` or a
   numeric p-value already captured on `StudyRow`), deprecating the conflated `state` (keep it as a
   derived/back-compat alias). Consumers that only need colour read `direction`; those that need
   evidence strength read `significance`. **Consumer-side interim** (just-dna-lite): the report now
   derives its benefit colour/sign from `state` treating `protective`→beneficial, `risk`→risk, and
   everything else (incl. `significant`) as neutral, with a numeric `weight` taking precedence when
   present — so weight-less protective modules render correctly without a fabricated effect size.

## The 1.0 cleanup (candidate tracker)

The **compatibility policy** — additive within a major, breaking cleanup only at a major bump, the
two-step deprecate→remove default — is a durable rule and lives in
[`CONSTITUTION.md`](CONSTITUTION.md) (Principle 3). This section is only the **living tracker**
of concrete items queued for the `→ 1.0` break; add candidates here as they surface.

Two version axes to reconcile at package `1.0`: `schema_version` is `"1.0"` while the packages are
`0.x`. Align them, or document explicitly that they track different things (wire format vs. package
release).

### 1.0 cleanup candidates (collecting — add as they surface)

| Candidate | Why | Proposed disposition |
|---|---|---|
| `VariantRow.state` | Overloaded legacy field; becomes a derived alias of `direction` in 0.3. | Deprecate at 1.0 (still read) → remove at 2.0, once consumers read `direction`/`stat_significance`. |
| `state` values `alt` / `ref` | Genotype-relative descriptors that never belonged; recoverable from `ref`/`alts`/`genotype`; 0.3 stops emitting them. | Drop from the accepted read-vocabulary at 1.0. |
| `VariantRow.pathogenic` / `benign` booleans | Lossy (can't express `likely_*`/`uncertain`); become derived aliases of `clin_sig` in 0.3. | Deprecate at 1.0 → remove at 2.0. (`clinvar` provenance boolean stays.) |
| `StudyRow.p_value: str` | Untyped string holding a number; can't be compared/sorted numerically. | Add a numeric companion in 0.x if needed; retype/remove the string at 1.0 (breaking). |
| `weights.parquet` `end` column | Always set equal to `start` — no source column feeds it. | Remove outright at 1.0 (artifact-digest change, major-only) or wire it to a real end coordinate. |
| `weights.parquet` `likely_pathogenic` / `likely_benign` | Always `False`; no CSV column feeds them — dead output. | Remove at 1.0, or wire to the new `clin_sig` tier. |
| `VariantRow.weight` vs `effect_size` | Potential confusion — module-local score vs published magnitude (0.3 keeps both, documented). | Review at 1.0 whether `weight` stays or is subsumed by `effect_size`. |
| Deprecated 0.3 flag/vocab aliases | Any transitional vocab kept for 0.x compat (e.g. the trimmed-vs-full `state` set). | Collapse to the canonical vocab at 1.0. |
