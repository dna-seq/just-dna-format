# Use cases & dogfooding — feasibility and blocker analysis

For each real or desired use case: **is it enabled by the format as it stands (0.4), and if not, what
is missing?** The point is to separate three things that get conflated —

- work the format **already enables** (author it today),
- work that is a **consumer** concern the format deliberately does not own (the data-agnostic north
  star — see [`CLAUDE.md`](../CLAUDE.md)), so there is *nothing to add*, and
- genuine **gaps** that need an additive format change.

Every gap below is tagged `→ RMn` and collected in *Roadmap items surfaced* at the end; those are the
items to migrate into [`ROADMAP.md`](ROADMAP.md).

## The feedback → schema cycle (where this doc sits)

The design docs are stages of **one loop**; an idea moves left-to-right as it matures:

1. **Feedback** — a consumer's field report. → [`CONSUMER_FIELD_NOTES.md`](CONSUMER_FIELD_NOTES.md),
   [`CONSUMER_ROUND2_AND_0_5.md`](CONSUMER_ROUND2_AND_0_5.md)
2. **Usage → blockers → solvability** — run each use case against the current bricks: is it *enabled*,
   *consumer-side*, or a *gap*; and is the gap closable **additively**? → **this doc**
3. **Means → draft schema → decision** — for a gap worth closing, the proposed shape + a charter check
   + the open questions to settle it. → [`PROPOSAL_0_4.md`](PROPOSAL_0_4.md)
4. **Conclusion — "how to do it now, with these bricks"** — the distilled worked example once the shape
   is settled. → [`REFERENCE_EXAMPLES.md`](REFERENCE_EXAMPLES.md)
5. **Terminal**, one of two:
   - **Fixed** — schema + compiler shipped (the models; [`COMPILER.md`](COMPILER.md) marks it
     validated/materialized), **or**
   - **Deferred** — a recognised gap parked as a roadmap item (`RMn` → [`ROADMAP.md`](ROADMAP.md)) when
     the means aren't worth building yet.

So **this doc and `REFERENCE_EXAMPLES.md` are the same use cases at two points in the loop** — here
they are *questions* (what blocks?), there they are *answers* (author it like this). An **ENABLED** /
schema-ready row here graduates to a `REFERENCE_EXAMPLES` entry; a **GAP** row graduates to
`PROPOSAL_0_4` (if being closed now) or an `RMn` roadmap item (if deferred). The loop is why a
"blocker" is never a dead end: it is either dissolved (it was consumer-side all along), closed
additively, or explicitly parked.

**Verdict legend**
- **ENABLED** — authorable/usable on 0.4 now, no format change.
- **CONSUMER-SIDE** — a consumer (runner/app) feature; the format correctly owns nothing here (per the
  north star). No format change — often no blocker at all.
- **SCHEMA-READY / COMPILER-PENDING** — the schema models express it; only the deferred compiler
  materialization (new parquet + round-trip) is missing. One known gap, not per-use-case.
- **GAP** — needs an additive format addition (the interesting rows).

A recurring result: most "can the format do X?" questions dissolve into CONSUMER-SIDE, because the
module is declarative annotation and the *doing* is a consumer's. The format earns its keep by the
properties it froze (declarative-not-code, integrity-as-identity, the `unresolved`/callability
contract), which are what make a consumer's X *safe and reproducible* — not by hosting X.

---

## 1. The consumer's 0.5 suggestions, each run through the lens

### 1a. Verification harness — run a module against N VCFs, emit report-card diffs (round-2 §3b)

**Verdict: CONSUMER-SIDE — no blocker, no format deliverable.** This is the headline dogfooding use
case and it is *already enabled*. Walk the requirements:

- *A panel is a set of loci + expected genotypes/bins* → **already a module** (a `variants.csv` of
  genotype→conclusion rows, or a binning table of measure→phenotype). No new "panel type".
- *Deterministic extraction of the observed value from a VCF* → the consumer's job, and `source_field`
  (0.4) now names the exact VCF `FORMAT`/`INFO` field to read, removing the last glue.
- *Trustworthy before/after (per-caller, ±liftover) diffs* → `artifact.digest` already gives the module
  a content identity, so a report-card diff is a byte-level diff of two deterministic runs.
- *No-call ≠ mismatch* → the mandatory `unresolved` outcome + the callability contract already stop a
  "no-call under caller B" from masquerading as a "mismatch vs caller A".

The one thing that *looked* like a format artifact — a standardized **evaluation-output / report-card
schema** (`{locus, observed, callability, bin_selected, verdict}`) — is **per-sample results, i.e. a
measurement**, so the north star keeps it consumer-side. It belongs in `just-dna-lite`, not
`just-dna-format`. **Nothing to schedule in the format.** `→ RM7` records the consumer-side schema so
it is not mistaken for a format item.

### 1b. Augmented-VCF as the landing pad for cracked short-read loci (round-2 §3c)

**Verdict: ENABLED at the format boundary; emission is CONSUMER-SIDE.** A caller emits its niche
genotype (PER3 span, DAT1 motif-path, MAOA half-repeat) as a synthetic VCF record (`<STR>` with
`INFO/RU`, `FORMAT/REPCN`, custom evidence fields); a `repeat_alleles.csv` module consumes it via the
same `source_field=REPCN` path as ExpansionHunter. The format does not invent a representation — it
*binds to* the VCF one. Producing the augmented VCF is the caller's job (consumer-side). The only
format touch-point (`source_field`) shipped in 0.4. Consuming **symbolic** alleles (`<STR n>`,
`<CNV>`) at the *count/dosage* layer is enabled via the binning tables; representing a symbolic allele
inside a `VariantRow.genotype` is not (see §3b) `→ RM5`.

### 1c. Callability three-state, phasing-aware panels, trio/multi-sample (round-2 §3d)

- **Callability three-state (covered-hom-ref vs no-call):** **CONSUMER-SIDE**, derivable from VCF
  `DP`/`GQ`/`FT` (or a gVCF ref-block). The format's part: `requires_callable` (reserved flag) marks
  rows where absence is informative; promoting it to a typed boolean column and reserving
  `callable_from` (the DP,GQ,FT signal) are the format-side follow-ups `→ RM6`.
- **Phasing-aware panels:** **ENABLED** — the `phased` flag + the phased genotype form `A|G` (0.3
  item 5b) already let a runner do cis/trans for compound-het and star-allele phasing (`*2x2/*4` vs
  `*2/*4x2`). No gap.
- **Trio / multi-sample (Mendelian / de-novo assertions):** **CONSUMER-SIDE** — VCF is natively
  multi-sample; the assertion runner is a consumer. An optional declarative *inheritance-expectation*
  field on a panel row would let the module carry the assertion as data rather than consumer lore —
  small, additive, optional `→ RM10` (only if a real module needs it).

### 1d. Authoring-support suggestions (from the just-dna-agents integration, ROADMAP obs 2026-07-10)

- **A canonical machine/LLM-facing authoring reference.** Consumers (MCP servers, agents, docs)
  hard-code prose summaries of the DSL that **drift** from the real schema. **ADOPTED (RM8, shipped in
  the 0.4 sample):** `just_dna_format.reference.authoring_reference()` returns a JSON-serialisable
  summary — every model's field list + all vocabularies + reserved names + the palette — **generated
  from the live models**, so it cannot drift; `json_schemas()` gives the full JSON Schema. A consumer's
  `get_spec_format` renders this instead of a hand-maintained blob.
- **A recommended icon/color palette.** `Display` validates `icon_set`/`color` but shipped no
  *recommended enumerated palette*, so each authoring tool invented one. **ADOPTED (RM9, shipped in the
  0.4 sample):** `manifest.RECOMMENDED_COLORS`/`RECOMMENDED_ICONS` (curated `semantic-use → value`
  maps, recommendation-only — not enforced), surfaced through `authoring_reference()`.

---

## 2. Reference-data-backed module types

### 2a. ClinVar gene-panel (flag pathogenic variants in a gene set)

**Verdict: SCHEMA-READY (interface) / GAP (native materialization).** `GenePanelSpec` (`source`,
`reference`, `reference_sha256`, `genes`, `significance`) already declares the panel and is recorded
verbatim in the manifest. Today an *app-side* adapter (`just-dna-lite`) enumerates the matching ClinVar
pathogenic/likely-pathogenic variants into `variants.csv`; the compiler does **not** resolve the panel
itself. **Missing:** native compile-time materialization (gene set + significance predicate →
`weights.parquet`) gated on a working, content-pinned ClinVar reference mixin `→ RM4`. Until then the
use case is fully reachable *through the app-side adapter* — so it is enabled in practice, with the
native path a convenience/quality follow-up.

### 2b. PharmGKB drug-response annotation (item 9)

**Verdict: ADOPTED (RM3, shipped in the 0.4 sample).** A PharmGKB row maps a variant/diplotype → a
**drug** + a **response/phenotype** + a PharmGKB **evidence level** (`1A`…`4`, `VALID_EVIDENCE_LEVELS`)
— a different axis from a risk weight. Built as a **dedicated `PharmVariantRow` (`pharm_variants.csv`)**
for single-variant drug response (keeps the SNP core clean — one CSV = one concern), plus optional
`drug`/`response`/`evidence_level` columns on `DiplotypeRow` for the diplotype-keyed case. A PharmGKB
module has **no empty `variants.csv`**. `evidence_level` is a *third* significance-flavoured axis,
distinct from `stat_significance`/`clin_sig` (orthogonal-axes discipline, Principle 5). Materialization
deferred with the rest of 0.4.

---

## 3. Composite modules (the real pipeline shapes)

### 3a. SNP + PRS in one module

**Verdict: ENABLED (RM1 + RM2 shipped).** A module is a *directory of CSVs* carrying both
`variants.csv` (`VariantRow`) and `pgs.csv` (`PgsRow`), joined on the shared `trait_efo_id` (item 5) so
a variant panel and its PRS companion sit in one content-addressed unit. The compiler now materializes
every present table kind to parquet (round-trip lossless) and treats `variants.csv` as optional, so
composed and single-domain modules both compile. No blocker.

*Composition principle (settled during the PharmGKB decision, now in CLAUDE.md): a module composes
from **optional** table kinds — one CSV = one concern — so the SNP core (`variants.csv`+`studies.csv`)
stays minimal and no module ever carries an empty `variants.csv` or a foreign domain's columns just to
host one table. This is the human-authorable half of the `RM2` work.*

### 3b. SNP + indels

**Verdict: ENABLED for small ACGT indels; GAP for structural/symbolic.** `VariantRow` alleles are
`^[ACGT]+$` **multi-base**, so a small insertion/deletion is expressible today (`ref=A, alts=AT`,
genotype `A/AT`) on the same `variants.csv` as SNPs — a mixed SNP+indel panel is authorable now. What
is *not* expressible: **symbolic/large structural** alleles (`<DEL>`, `<INS>`, `<DUP>`, repeat
expansions as `<STR>`) — there is no symbolic-allele genotype. Those route through the copy-number /
repeat binning tables (dosage/count, not sequence) or await a symbolic-allele representation
`→ RM5`. So: everyday SNP+indel modules need nothing; SV-scale variation is the recognised gap.

### 3c. SNP + PRS + PGx + CNV in one "personal panel"

**Verdict: ENABLED (RM1 + RM2 shipped).** The generalization of 3a: a personal/curated module mixing
`variants.csv`, `pgs.csv`, `activity_phenotype.csv`/`diplotypes.csv`, and `copynumbers.csv`, all joined
on `trait_efo_id`, compiles today — each present kind materializes to parquet with round-trip. This is
exactly the "personal module re-checked deterministically on every pipeline change" the verification
harness (§1a) wants — and RM1/RM2 are what unlocked it.

---

## Roadmap items surfaced

The gaps above, consolidated. Format-side items migrate into [`ROADMAP.md`](ROADMAP.md); the
consumer-side one is recorded so it is not mistaken for a format task.

| # | Item | Kind | Unblocks | Priority |
|---|---|---|---|---|
| RM1 | ✅ **shipped** — compiler materializes all 0.4 tables → parquet with lossless round-trip (generic `_build_table`/`_write_table_csv` over `_TABLE_KINDS`) | format (compiler) | 3a, 3c, harness on binned loci | done |
| RM2 | ✅ **shipped** — composed modules: `variants.csv` optional, a module carries only the kinds it uses (no empty `variants.csv`); `studies.csv` required iff variants present | format (compiler) | SNP+PRS, personal panels | done |
| RM3 | ✅ **shipped in 0.4 sample** — `PharmVariantRow` (`pharm_variants.csv`) + `drug`/`response`/`evidence_level` on `DiplotypeRow` | format (schema) | 2b | done |
| RM4 | **Native ClinVar gene-panel materialization** + content-pinned reference mixin (item 7 follow-up) | format (compiler) + consumer ref | 2a (native path) | medium |
| RM5 | **Symbolic/structural alleles** (`<S>`/`<L>`/`<DEL>`/`<INS>`/`<DUP>`/`<STR>`; large indels) — a representation beyond `^[ACGT]+$`. **Motivating case: 5-HTTLPR** (S/L not nucleotides → rejected today) | format (schema) | 3b (SV), 1b (symbolic consume), 5-HTTLPR | medium |
| RM6 | Promote `requires_callable` to a typed boolean column; reserve/build `callable_from` (DP,GQ,FT three-state) | format (schema) | 1c callability | low-medium |
| RM7 | **Evaluation-output / report-card schema** for the verification harness | **consumer** (`just-dna-lite`), NOT the format | 1a | — (not a format task) |
| RM8 | ✅ **shipped in 0.4 sample** — `reference.authoring_reference()` + `json_schemas()`, generated from the live models | format (schema) | 1d drift | done |
| RM9 | ✅ **shipped in 0.4 sample** — `manifest.RECOMMENDED_COLORS`/`RECOMMENDED_ICONS` | format (schema) | 1d palette | done |
| RM10 | Optional declarative inheritance-expectation field (trio/de-novo assertion as data) | format (schema) | 1c trio | low (only if needed) |

**Takeaway.** The two load-bearing items — **RM1 + RM2** (compiler materialization + composed
modules) — are now **shipped**: the frozen 0.4 shapes are runnable artifacts, and every
composite/personal module compiles with lossless round-trip. What remains open is small and clearly
scoped: RM3-adjacent extensions, RM5 (symbolic alleles / 5-HTTLPR), and RM6/RM10 refinements. Notably,
the format's *purpose expansion* (the verification harness) still needs **no format change** — it rides
on the properties already frozen, now with the tables materialized under it.
