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

## 4. Network-first validation & enrichment (external-source scrutiny)

### 4a. `just-module-validator` — deterministic source-checks + provenance enrichment against public sources

**Verdict: the validator is CONSUMER-SIDE (Principle 2 keeps it out of these libs); the two additive
format anchors it needs shipped in 0.4 (RM11/RM12), and one requiredness fix waits for 1.0.**

A proposed sibling library that is **network-first**: given a module it checks the authored claims
against public sources and enriches them —

- validate every `pmid` resolves in PubMed, and every `rsid` resolves in dbSNP at the authored
  `chrom:start` (flag coord/liftover drift);
- cross-fill provenance ids — derive a `doi` from a PMID and vice-versa;
- confirm a study's claim actually appears in the cited article's fulltext (imagine further
  source-checks in the same spirit).

By the data-agnostic north star and **Principle 2 (no network; inject-only)**, the *doing* — every
fetch and lookup — is a consumer's, and can never live in `just-dna-format`/`just-dna-compiler`
(that would pull the network dependency the tiers forbid, Goal 2). So the validator is a new
consumer/enricher sibling to `just-dna-lite`, recorded as `→ RM13` so it is not mistaken for format
scope — exactly as the report-card harness is (§1a / RM7). Crucially, **most of what it checks needs
nothing from the format**: `rsid`, `chrom`, `start` already exist, so validating them against dbSNP
is pure consumer work — enabled today. Two things it wants to *anchor* are genuine additive format
gaps, and one is a 1.0 requiredness fix:

- **`doi` as a provenance id — additive, shipped in 0.4 (RM11).** `StudyRow` previously carried only
  `pmid` (required, and it must contain ≥1 real PubMed id). DOI is *wider*: it covers preprints
  (bioRxiv/medRxiv), books, theses, and datasets that have no PMID. The **optional `doi` column** now
  lets the validator record and cross-fill it, and lets a module cite a DOI-bearing source. Purely
  additive → P3/P8 clean (new optional field; existing data still validates); validated against the
  DOI grammar and kept verbatim. `→ RM11`.

- **A provenance *locator* — search-phrase/regex pointing at the passage in fulltext — additive,
  shipped in 0.4 (RM12).** So the validator can answer *"does the cited article's fulltext actually
  contain this claim?"* in a yes/no manner, a study row now carries optional **`provenance_quote`**
  (keyword phrase) and **`provenance_regex`**. The regex sits squarely inside **Principle 1's
  sanctioned escape hatch**: a *declarative pattern grammar* is **data, not code** — the module ships
  the pattern, the consumer supplies the fulltext and runs the match, evaluated by a **linear-time /
  ReDoS-safe engine** (P1's explicit requirement; the compiler only `re.compile`-checks it at author
  time). It is the provenance analogue of `source_field` (0.4): `source_field` is a declarative
  pointer to *where the measurement lives in a VCF*; the locator is a declarative pointer to *where
  the claim lives in the article*. Neither holds the data it points at (north star ✓). Primarily an
  aid for **LLM-authors** (which can emit a precise pattern), yet a plain keyword phrase is legible
  enough to clear the human-authorability gate for a human author too. `→ RM12`.

- **`pmid` is mandatory today — the DOI-only case cannot be closed additively (a 1.0 fix).** `pmid:
  str` is *required and must parse to a real PubMed id* (`extract_pmids`), so a **preprint/book/thesis
  with only a DOI is unauthorable right now** — and demoting a required field to optional is precisely
  the move Principle 8 forbids within a major. Adding `doi` (RM11) is necessary but **not sufficient**:
  while `pmid` stays required-and-PMID-shaped, DOI-only provenance is still rejected. The full fix is
  **doi-first at 1.0** — make `pmid` optional/legacy and require **at least one of `{doi, pmid}`**
  ("not every citation has a PMID, but every citation has a stable id" — the reverse of today's rule).
  That is a requiredness change → **major-only**, parked as a **1.0-cleanup candidate**, not an `RMn`.
  Until 1.0, DOI-only provenance is an explicitly-parked gap.

---

## 5. Module-level authorship & provenance (author-kind → scrutiny calibration)

### 5a. Structured per-version authorship — who *created* / *edited* / *audited*, and whether each is AI or a human expert

**Verdict: SHIPPED in 0.4 (RM14) — an additive, digest-neutral `authorship` record; the old flat
fields stay for compat.** This is the module-level companion to the
network-first validator (§4a): the validator — and a marketplace review queue, and a human auditor —
needs to **route its scrutiny by who authored the version**, because *AI and human error-spectra
overlap but differ*. An AI author fabricates plausible-but-wrong PMIDs / rsids / effect-sizes (exactly
the checks RM11–RM13 automate); a human expert makes transcription / off-by-one / stale-reference
slips. The format never *performs* the scrutiny (consumer-side, north star) — it must *carry the
author-kind* so the consumer can select the right profile, the same "annotate so the consumer's X is
safe and reproducible" contract as everywhere else.

What exists today, and why it does not cover it:

- `ModuleManifest.authors: list[str]` — a **flat** list: no role (created/edited/audited), no kind
  (AI/human). The overloaded-axis anti-pattern (P5), at the list level.
- `curator` / `method` — single free-form strings; `Defaults.curator` even **defaults to
  `"ai-module-creator"`, smuggling author-kind into a string** a consumer cannot reliably facet on.
  This is precisely the axis-overload Principle 5 exists to unwind.
- `Provenance` (`generator`/`model`/`agent_version`) + per-variant `ProvenanceItem.human_reviewed` —
  captures *AI-generation* and *per-variant human review*, but not module-level **role attribution**
  (who edited vs. audited *this* version), and it names only the AI side.

So the axes were half-present and tangled. The shipped shape is a **structured, per-version
`authorship` list** (`Contribution` model) unbundling three orthogonal axes (P5): **identity** (`who`),
**role** (`created | edited | audited | reviewed`, a closed vocab), and **kind** — a *multi-valued,
open* tag set with a recommended seed: a **human ladder of assurance** `human` → `human_expert` →
`human_certified` (medically / board-certified, e.g. a clinical geneticist), or `ai` plus a scale tag
`agent`/`team`/`swarm`. There is deliberately **no `hybrid` tag** — it was rejected as non-explicit
(hybrid *what*?); a joint contribution is **two entries** (a human and an ai), each with its own
`kind`, so the mix is always spelled out. Each entry is optionally timestamped (`at`). "Per-version"
falls out of immutability (P4): a version's manifest records its own authorship, and cross-version
history is the union via `aggregate_provenance`.

**Why it is cheap.** `artifact.digest` is a Merkle root over the **parquet files only** — manifest
metadata (`logs`, `provenance`, `logo`, and this) is deliberately *out* of it. So two versions with
identical annotation content but different authorship keep the **same content identity** (correct: who
authored ≠ what the annotation is). Adding it is additive/optional (P3/P8), touches no parquet column,
and is **digest-neutral even after 0.4 freezes**. `curator`/`authors`/`provenance` stay working;
folding the flat `authors` into the structured record is a 1.0-cleanup candidate. `authoring_reference()`
picks up the new vocabularies automatically.

**Charter check:** data-agnostic ✓ (module metadata, not sample data); declarative ✓; P5 — this *is*
the axis-unbundling; P6 — `role`/`kind` are `frozenset` vocabularies; the human-authorability gate is
met by keeping the whole block optional and collapsing it to a single entry for the common
one-AI-author case, so a module never reads like an enterprise audit ledger. Like `panel`, it is
manifest metadata and is *not* reconstructed by the lossy parquet→spec `reverse_module` (which rebuilds
a content skeleton) — the durable per-version record is the manifest itself, which is correct and no P7
issue (P7 governs artifact columns). `→ RM14` (**shipped**).

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
| RM11 | ✅ **shipped in 0.4** — **`doi` provenance column** on `StudyRow` (optional; validated against the DOI grammar, kept verbatim) | format (schema) | 4a | done |
| RM12 | ✅ **shipped in 0.4** — **Provenance locator**: optional `provenance_quote` (keyword phrase) + `provenance_regex` (author-time-compiled, matched by a consumer-side linear-time engine — P1 pattern grammar) on `StudyRow` | format (schema) | 4a | done |
| RM13 | **`just-module-validator`** — network-first source-check/enrichment library | **consumer** (new sibling), NOT the format | 4a | — (not a format task) |
| RM14 | ✅ **shipped in 0.4** — **Structured per-version authorship** (`authorship: [Contribution]`): `{who, role, kind, at}`; role closed {created/edited/audited/reviewed}; kind open, seed = human ladder {human, human_expert, human_certified} / {ai}+scale {agent,team,swarm} (no `hybrid` — joint = two entries). Manifest metadata → **digest-neutral**. | format (schema) | 4a validator, marketplace review | done |

**Takeaway.** The two load-bearing items — **RM1 + RM2** (compiler materialization + composed
modules) — are now **shipped**: the frozen 0.4 shapes are runnable artifacts, and every
composite/personal module compiles with lossless round-trip. What remains open is small and clearly
scoped: RM3-adjacent extensions, RM5 (symbolic alleles / 5-HTTLPR), RM6/RM10 refinements, and the two
provenance anchors RM11/RM12 (`doi` + fulltext locator) that let a network-first validator scrutinise
a module without the format ever fetching. Notably,
the format's *purpose expansion* (the verification harness) still needs **no format change** — it rides
on the properties already frozen, now with the tables materialized under it.
