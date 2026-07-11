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
case against the shipped 0.4 bricks. RM1/RM2/RM3/RM8/RM9 **shipped in 0.4**; the items still open:

| # | Item | Owner | Motivating use case | Effort |
|---|---|---|---|---|
| RM4 | **Native ClinVar gene-panel materialization** — compile a `GenePanelSpec` (gene set + significance predicate) into `weights.parquet` at compile time, gated on a **content-pinned ClinVar reference mixin**. The 0.2 `GenePanelSpec` *interface* ships and is recorded verbatim; the app-level `gene_panel` adapter in just-dna-lite is the interim reference implementation. Blocked only by Constitution P2 (no network) — the reference must be *injected*, not fetched. | format (compiler) + consumer-provided reference | gene-panel modules (cardio / cancer / pathogenic) | medium |
| RM5 | **Symbolic / structural alleles** — a representation beyond `^[ACGT]+$`: `<S>`/`<L>`, `<DEL>`/`<INS>`/`<DUP>`, `<STR n>`, and large indels. **Motivating case: 5-HTTLPR** (a biallelic ~43 bp structural indel → Short/Long, *not* a repeat count; rejected by today's nucleotide grammar and a category error in `repeat_alleles.csv`). Also unblocks SV-scale variation and consuming symbolic VCF alleles (round-2 §1b/3c). | format (schema) | 5-HTTLPR, SNP+SV modules, symbolic-VCF consume | medium |
| RM6 | **Callability as first-class state** — promote `requires_callable` from an optional flag to a queryable typed column, and build the reserved **`callable_from`** (the DP,GQ,FT three-state signal from round-2 §3d). The consumer's own oracle enum (`CONFIRMED_NEGATIVE`/`LOW_DP_NEG`/`UNCOVERED`) is why "a named negative is assertable only where proof is `CONFIRMED_NEGATIVE`" — consumers *will* filter on it. | format (schema) | callability / no-call ≠ hom-ref | low-medium |
| RM10 | **Declarative inheritance-expectation field** — an optional trio / de-novo / Mendelian-consistency assertion carried *as data* (the panel says what it expects; a consumer checks it). Only if a real module needs it. | format (schema) | trio / multi-sample panels | low (on demand) |
| RM7 | **Evaluation-output / report-card schema** for the verification harness — **NOT a format task.** Per-sample results are a *measurement*, so by the data-agnostic north star this is a **consumer** contract (`just-dna-lite`), listed here only so it is not mistaken for format scope. | consumer (`just-dna-lite`) | verification harness (§1a) | — |

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
Principle 5), these names are reserved against the one-way door and **must not** be claimed early or
smuggled in as `flags`. Audit every new name against this list before adding it.

**Enforced now** (rejected via `model_config = ConfigDict(extra="forbid")` on the 0.4 tables; the live
set is `just_dna_format.vocab.RESERVED_NAMES_0_4`):
- **`caller` / `caller_version` / `reference_db`** — the provenance triple describes which tool made a
  *call* (a consumer's computed measurement), not annotation → consumer-side by the data-agnostic north
  star; reserved as **three** columns (consumers filter each independently — round-2 Q2), never one
  composite string.
- **`callable_from`** — the VCF-derived three-state callability signal (DP, GQ, FT); reserved for
  RM6/round-2 §3d.

**Planned future annotation axes** (not yet built; reserve the names so they survive the one-way door):
- **`consequence`** — VEP molecular consequence (Sequence-Ontology term, e.g. `missense_variant`).
  Distinct from `direction` (phenotypic) and `clin_sig` (clinical). **Never repurpose the bare word
  `effect`** for it.
- **`impact`** — VEP impact `{HIGH, MODERATE, LOW, MODIFIER}`, derived from `consequence`.
- **`allele_frequency`** (+ **`af_population`**) — gnomAD-style MAF context.

*(The ploidy / non-SNV quantities that were reserved through 0.3 — `allele_fraction` / heteroplasmy,
`repeat_count` + `repeat_unit`, copy-number dosage — are **built** as the 0.4 binning primitive; the
`hemizygous` genotype case ships via the widened single-allele genotype. Symbolic/structural alleles
remain open as RM5.)*

## The 1.0 cleanup (candidate tracker)

The **compatibility policy** — additive within a major, breaking cleanup only at a major bump, the
two-step deprecate→remove default — is a durable rule in [CONSTITUTION.md](CONSTITUTION.md)
(Principle 3). This is the **living tracker** of concrete items queued for the `→ 1.0` break; add
candidates as they surface.

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
