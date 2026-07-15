# just-dna-format — Roadmap

Forward-looking plans for the schema contract + reference compiler. **This doc is forward-only:**
what already shipped (0.1.0 → 0.4.0) and the rationale behind it now live where they belong —

- **[CHANGELOG.md](CHANGELOG.md)** — what shipped in each release, newest first (the record of
  0.1–0.4 that this doc used to duplicate).
- **[COMPILER.md](COMPILER.md)** — the per-feature coverage table (validated / materialized / computed).
- **[PROPOSAL_0_4.md](PROPOSAL_0_4.md)** + **[CONSUMER_ROUND2_AND_0_5.md](CONSUMER_ROUND2_AND_0_5.md)**
  — the 0.4 design rationale and the round-2 answers.
- **[USE_CASES.md](USE_CASES.md)** — each use case run through the *what-blocks?* lens (the `RMn`
  items below are derived there); **[REFERENCE_EXAMPLES.md](REFERENCE_EXAMPLES.md)** — worked drafts.

Code comments that cite "ROADMAP item N" / "ROADMAP 0.3 item 5b" are historical breadcrumbs for
already-shipped features — follow them to CHANGELOG.md / COMPILER.md.

**Status:** treating the current branch as **0.4-rc** (packages at `0.4.0`, unpublished;
`schema_version` `"1.0"`). Everything below is 0.5-and-beyond scope plus the open idea-book.

## 0.5 scope — deferred roadmap items (`RMn`)

Derived in [USE_CASES.md](USE_CASES.md) ("Roadmap items surfaced") by running each real/desired use
case against the shipped 0.4 bricks. RM1/RM2/RM3/RM8/RM9/RM11/RM12/RM14 **shipped in 0.4** (their
rows below are kept for traceability, marked ✅); the rest are 0.5-and-beyond scope:

| # | Item | Owner | Motivating use case | Effort |
|---|---|---|---|---|
| RM4 | **Native ClinVar gene-panel materialization** — compile a `GenePanelSpec` (gene set + significance predicate) into `weights.parquet` at compile time, gated on a **content-pinned ClinVar reference mixin**. The 0.2 `GenePanelSpec` *interface* ships and is recorded verbatim; the app-level `gene_panel` adapter in just-dna-lite is the interim reference implementation. Blocked only by Constitution P2 (no network) — the reference must be *injected*, not fetched. | format (compiler) + consumer-provided reference | gene-panel modules (cardio / cancer / pathogenic) | medium |
| RM5 | **Symbolic / structural alleles** — a representation beyond `^[ACGT]+$`: `<S>`/`<L>`, `<DEL>`/`<INS>`/`<DUP>`, `<STR n>`, and large indels. **Motivating case: 5-HTTLPR** (a biallelic ~43 bp structural indel → Short/Long, *not* a repeat count; rejected by today's nucleotide grammar and a category error in `repeat_alleles.csv`). Also unblocks SV-scale variation and consuming symbolic VCF alleles (round-2 §1b/3c). | format (schema) | 5-HTTLPR, SNP+SV modules, symbolic-VCF consume | medium |
| RM6 | **Callability as first-class state** — promote `requires_callable` from an optional flag to a queryable typed column, and build the reserved **`callable_from`** (the DP,GQ,FT three-state signal from round-2 §3d). The consumer's own oracle enum (`CONFIRMED_NEGATIVE`/`LOW_DP_NEG`/`UNCOVERED`) is why "a named negative is assertable only where proof is `CONFIRMED_NEGATIVE`" — consumers *will* filter on it. | format (schema) | callability / no-call ≠ hom-ref | low-medium |
| RM10 | **Declarative inheritance-expectation field** — an optional trio / de-novo / Mendelian-consistency assertion carried *as data* (the panel says what it expects; a consumer checks it). Only if a real module needs it. | format (schema) | trio / multi-sample panels | low (on demand) |
| RM14 | ✅ **shipped in 0.4** — **Structured per-version authorship**: an optional `authorship: [Contribution]` on `module_spec.yaml`/`ModuleManifest`, unbundling the flat `authors` + free-form `curator` (which smuggled kind via the `"ai-module-creator"` default) into three orthogonal axes (P5): **identity** (`who`), **role** (closed vocab created/edited/audited/reviewed), **kind** (open, multi-valued: human ladder `human`→`human_expert`→`human_certified`, or `ai`+scale `agent`/`team`/`swarm`; no `hybrid` — a joint contribution is two entries). Motivating case: **AI and human error-spectra overlap but differ**, so a consumer (the RM13 validator, a marketplace review queue, a human auditor) routes scrutiny by author-kind — the format carries the kind, the consumer picks the profile (north star). **Digest-neutral** (manifest metadata, out of `artifact.digest`); like `panel`, not reconstructed by the lossy `reverse_module`. Folding the flat `authors`/`curator` in is a 1.0-cleanup candidate. | format (schema) | authorship-aware scrutiny (§5a) | done |
| RM7 | **Evaluation-output / report-card schema** for the verification harness — **NOT a format task.** Per-sample results are a *measurement*, so by the data-agnostic north star this is a **consumer** contract (`just-dna-lite`), listed here only so it is not mistaken for format scope. | consumer (`just-dna-lite`) | verification harness (§1a) | — |
| RM11 | ✅ **shipped in 0.4** — **`doi` provenance column** on `StudyRow`, wider than `pmid` (covers preprints/books/theses/datasets with no PubMed id); validated against the DOI grammar, kept verbatim, materialized into `studies.parquet`. A network-first validator (RM13) cross-fills `doi`↔`pmid`. Additive/optional → P3/P8 clean. The full DOI-only fix (relaxing the mandatory `pmid`) is a 1.0 item — see the 1.0 tracker. | format (schema) | validator source-checks (§4a) | done |
| RM12 | ✅ **shipped in 0.4** — **Provenance locator**: optional `provenance_quote` (keyword phrase) + `provenance_regex` on `StudyRow`, pointing at the passage in the cited article's fulltext so a validator can answer *"does the fulltext contain this claim?"* yes/no. The regex is a **declarative pattern grammar** (Principle 1 — data, not code; `re.compile`-checked at author time, matched by a consumer-side ReDoS-safe engine); the provenance analogue of `source_field`. | format (schema) | validator fulltext check (§4a) | done |
| RM13 | **`just-module-validator`** — a network-first source-check/enrichment library (validate `pmid` in PubMed, `rsid`/coords in dbSNP, cross-fill ids, confirm fulltext provenance). **NOT a format task.** Principle 2 (no network) keeps all fetching in a **consumer** sibling to `just-dna-lite`; listed here only so it is not mistaken for format scope, and as the motivating consumer for RM11/RM12. | consumer (new sibling) | deterministic module scrutiny (§4a) | — |
| RM15 | **Build-agnostic identity & multi-build support (other-builds-support)** — today a coordinate is *implicitly GRCh38* (legacy-from-implementation): `genome_build` is authored/manifest metadata, but every `chrom/start/ref`, the Ensembl resolver, and all coord-based reasoning silently assume GRCh38. Coordinates are **not absolute** — GRCh37 / GRCh38 / T2T-CHM13 disagree, and the rsid↔coordinate mapping is **build-specific**: an rsid may resolve in one build and be un-annotatable (unplaced/absent) in another, and presence/absence combinations vary per build. This item makes the build a first-class axis — coordinates tagged by (or resolved per) build, a **build-aware resolver** (the injected reference declares its build; a module/reference build mismatch degrades to *unverified* rather than a false consistency error), and cross-build rsid annotatability recorded *as data*. **Parks the "coordinate-first identity" design (option C from the rsid↔coord identity discussion): anchoring identity on the coordinate is rejected while the format is single-build, because it would bake GRCh38 into `variant_key` and make identity reference-dependent; it becomes reconsiderable only once identity can name its build.** **Generalizes one-to-many rsid expansion to multi-build:** a no-coord rsid that maps to several loci is expanded to one row per locus (a paralog/SV signal a client can count — data-agnostic), and that ships **GRCh38-only now as compiler behavior** (pinned by `compiler_version`, not a schema break). What is build-specific is *which* loci and *how many*, so RM15 tags expanded coordinates by build and records cross-build annotatability; the GRCh38 expansion itself is not deferred. Blocked by nothing external (schema-shape + resolver decision) but large — touches identity, positions, the resolver, and `artifact.digest`. Interacts with RM5 (symbolic/structural alleles differ across assemblies) and the reserved `reference_db` axis. | format (schema + compiler) | GRCh37 / T2T modules; cross-build annotatability | large |

**Round-3 / on-demand (widen additively only if a real module hits it):**
- **STR microvariant notation** — forensic loci use `full.partial` allele names (TH01 `"9.3"` = 9 full
  `TCAT` repeats + 3 extra bases), which is *not* the decimal 9.3. A binning bound stays a plain
  magnitude for ordering; the `full.partial` allele *name* is a distinct string (a candidate for the
  reserved repeat motif-path / allele-string escape hatch), never smuggled into the float bound
  (CONSUMER_ROUND2 C2). Pathogenic-threshold loci (HTT CAG) are unaffected.

**Cross-repo (tracked elsewhere):** **just-dna-marketplace** — take `just-dna-compiler` as the M4
publish dependency; serve `logs` via the files endpoint; render the cross-version provenance union
(`aggregate.aggregate_provenance`) on the module-detail view.

## Freeform suggestions — the 0.5 idea-book

The consumer's grounded 0.5 ideas (kept inside the one constraint: **VCF-based, possibly augmented on
top**) live in full in [CONSUMER_ROUND2_AND_0_5.md](CONSUMER_ROUND2_AND_0_5.md) §3, each run through
the what-blocks lens in [USE_CASES.md](USE_CASES.md) §1. Standing dispositions:

- **3a — module declares where its measurement lives in a VCF.** ✅ Taken early: `source_field` shipped
  in 0.4 (an optional, `|`-alternatable **bare field-name token** on every binning table — a
  *declarative pointer, not an expression*, inside Principle 1). An ExpansionHunter VCF (`INFO/RU` →
  `repeat_unit`, `FORMAT/REPCN` → the measure) is consumable with zero glue.
- **3b — modules as a deterministic verification harness** (run a panel against N VCFs, emit a
  byte-diffable report-card). **The strongest idea, and it needs *nothing* from the format:** a panel
  is already a module, `source_field` names the field to read, `artifact.digest` makes the before/after
  diff trustworthy, and the mandatory `unresolved`/callability contract stops a no-call masquerading as
  a mismatch. It is a **consumer** feature (`just-dna-lite`); the format only supplies properties it
  already froze. Recorded as an *enabled* use case, not a gap.
- **3c — augmented-VCF as the landing pad** for cracked short-read loci (a synthetic `<STR>` record with
  `INFO/RU` + `FORMAT/REPCN` + custom evidence fields, consumed through the same `source_field=REPCN`
  path). Endorsed as the interface — the format binds to the VCF, it does not reinvent it. Consuming the
  *symbolic* alleles themselves is RM5.
- **3d — smaller VCF-native ideas:** callability three-state → RM6; phasing-aware panels → already
  expressible (the `phased` flag + VCF `PS`/`HP`); trio/de-novo assertion → RM10.

New ideas enter here as freeform suggestions, then graduate through the design cycle
(feedback → USE_CASES lens → PROPOSAL → shipped or parked as an `RMn` above).

## Reserved namespace

Because backward-compat makes column names and vocabularies **permanent within a major** (CONSTITUTION
Principle 5), a name expected to become a real **module column** later is reserved against the one-way
door and **must not** be claimed early or smuggled in as `flags`. This list is *only* for genuine
anticipated module-side axes — it is **not** a catalogue of names that "may not appear" (that space is
unbounded and pointless to enumerate; barring `caller` would be as arbitrary as barring `pasta_recipe`).
Audit every new name against this list before adding it.

**Enforced now** (the live set is `just_dna_format.vocab.RESERVED_NAMES_0_4`). Every authored model
inherits `AuthoredModel`, which sets `extra="forbid"` (rejects *any* unknown column) **and** runs the
`reject_reserved` before-validator, so a reserved name fails with a *specific* diagnosis — what it is
reserved for + that a release may claim it (`vocab.RESERVED_NAME_REASONS`) — while a random/misspelled
column gets the generic "extra inputs not permitted":
- **`reference_db`** — a module-side hint naming *which* reference database the app should join this
  annotation against when several exist (implicit Ensembl for variants / ClinVar for `clin_sig` today;
  a module may pin it, e.g. a specific PharmVar release). Annotation-side addressing, a real future axis.
- **`callable_from`** — the callability signal a consumer establishes a negative from (DP, GQ, FT);
  reserved for RM6/round-2 §3d as the typed successor to the built `requires_callable` flag.

*(`caller` / `caller_version` were reserved through the 0.4 draft as a "provenance triple" (round-2 Q2)
but are **dropped**: they name which tool produced a *call* — a consumer-side measurement, never module
annotation — so there is no future module axis to hold, and barring the bare name is arbitrary. A
consumer records them on its own call data; a module never carries them, and `extra="forbid"` rejects
them like any stray column. `reference_db` stayed because it has a real annotation-side meaning above,
not the caller-provenance one it was first reserved under.)*

**Planned future annotation axes** (documented intentions, **not yet in the enforced set** above — they
are rejected generically by `extra="forbid"` today, and get a slot + a specific diagnosis only when a
release actually commits to building them):
- **`consequence`** — VEP molecular consequence (Sequence-Ontology term, e.g. `missense_variant`).
  Distinct from `direction` (phenotypic) and `clin_sig` (clinical). **Never repurpose the bare word
  `effect`** for it.
- **`impact`** — VEP impact `{HIGH, MODERATE, LOW, MODIFIER}`, derived from `consequence`.
- **`allele_frequency`** (+ **`af_population`**) — gnomAD-style MAF context.

*(`doi`, `provenance_quote`, and `provenance_regex` were reserved here for RM11/RM12 and are now **built**
as optional `StudyRow` columns in 0.4 — so they are absent from this list. The **doi-first** flip that
relaxes the mandatory `pmid` remains a 1.0 item; see the 1.0-cleanup tracker.)*

*(The ploidy / non-SNV quantities that were reserved through 0.3 — `allele_fraction` / heteroplasmy,
`repeat_count` + `repeat_unit`, copy-number dosage — are **built** as the 0.4 binning primitive; the
`hemizygous` genotype case ships via the widened single-allele genotype. Symbolic/structural alleles
remain open as RM5.)*

## The 1.0 cleanup (candidate tracker)

The **compatibility policy** — additive within a major, breaking cleanup only at a major bump, the
two-step deprecate→remove default — is a durable rule in [CONSTITUTION.md](CONSTITUTION.md)
(Principle 3). This is the **living tracker** of concrete items queued for the `→ 1.0` break; add
candidates as they surface.

**Additivity has two axes.** A new version may expand the **column-set** (new optional columns —
routine, digest-only-move while unpublished) *and* the **row-set** (one authored row compiling to
several — e.g. a one-to-many rsid → one row per locus). Row-set expansion changes identity
*cardinality* but is **not** a schema break: it is resolver behavior pinned on the `compiler_version`
axis (P4 already pins the digest to the resolved reference), so the GRCh38 expansion ships now. Only
the *build-aware* generalization (which/how-many loci per build, cross-build annotatability) is RM15.
The idea is to pile genuinely rule-tripping edge-cases (requiredness demotions, retypes, identity-key
*semantics* changes) on the 1.0/RM15 piles instead of forcing them into a minor.

Version-axis note: `schema_version` is `"1.0"` while the packages are `0.x` (now `0.4.0`). At `1.0`,
either align them or document explicitly that they track different things (wire format vs. package
release).

| Candidate | Why | Proposed disposition |
|---|---|---|
| `VariantRow.state` | Overloaded legacy field; a derived alias of `direction` since 0.3. | Deprecate at 1.0 (still read) → remove at 2.0, once consumers read `direction`/`stat_significance`. |
| `state` values `alt` / `ref` | Genotype-relative descriptors that never belonged; recoverable from `ref`/`alts`/`genotype`; not emitted since 0.3. | Drop from the accepted read-vocabulary at 1.0. |
| `VariantRow.pathogenic` / `benign` booleans | Lossy (can't express `likely_*`/`uncertain`); derived aliases of `clin_sig` since 0.3 (now materialized tri-state). | Deprecate at 1.0 → remove at 2.0. (`clinvar` provenance boolean stays.) |
| `StudyRow.p_value: str` | Untyped string holding a number; can't be compared/sorted numerically. | Add a numeric companion in 0.x if needed; retype/remove the string at 1.0 (breaking). |
| `weights.parquet` `end` column | Always set equal to `start` — no source column feeds it. | Remove outright at 1.0 (artifact-digest change, major-only) or wire it to a real end coordinate. |
| `weights.parquet` `likely_pathogenic` / `likely_benign` | Always `False`; no CSV column feeds them — dead output. | Remove at 1.0, or wire to the `clin_sig` tier. |
| `VariantRow.weight` vs `effect_size` | Potential confusion — module-local score vs published magnitude (both kept, documented). | Review at 1.0 whether `weight` stays or is subsumed by `effect_size`. |
| Deprecated flag/vocab aliases | Any transitional vocab kept for 0.x compat (e.g. the trimmed-vs-full `state` set). | Collapse to the canonical vocab at 1.0. |
| `ModuleManifest.authors: list[str]` + free-form `curator` | Flat and overloaded — no role (created/edited/audited), no kind (AI/human); `Defaults.curator` smuggles kind via its `"ai-module-creator"` default. Superseded by the structured authorship record (RM14) once it ships. | Keep both as derived projections through 0.x (P8); at 1.0 fold `authors` into the structured record and drop the kind-smuggling `curator` default. |
| `StudyRow.pmid` required + PMID-shaped | Mandatory `pmid` (must parse to a real PubMed id) rejects DOI-only provenance — preprints (bioRxiv/medRxiv), books, theses, datasets. Demoting a required field is P8-forbidden in-major, so adding optional `doi` (RM11) alone can't unblock it. | **doi-first at 1.0**: make `pmid` optional/legacy and require **≥1 of `{doi, pmid}`** (every citation has a stable id, not necessarily a PMID; the reverse holds). Requiredness change → major-only. |
| Coordinate-first identity (option C) | Minimal B+ keys on **rsid when it uniquely identifies the row, else coordinate** (expanded/one-to-many and position-only rows are coord-keyed; rsid-1:1 and rsid+coord stay rsid-keyed → build-agnostic where possible). A globally coordinate-first key is more uniform but build-baked. | Reconsider coordinate-first only under RM15, once identity can name its build. Major (identity-*semantics* change). |
