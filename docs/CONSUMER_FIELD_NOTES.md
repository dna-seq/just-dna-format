# Field notes from a production WGS/genome-annotation pipeline

*A consumer's usability review of `just-dna-format`, plus additive schema proposals grounded in
working implementations of the hard loci the format currently reserves (PGx star-alleles, VNTR/STR
repeats, CNV dosage, mtDNA heteroplasmy, ancestry-conditional PRS, and call-confidence).*

**Status: external feedback / design input — not a shipped contract.** This document is written the
same way [`REFERENCE_EXAMPLES.md`](REFERENCE_EXAMPLES.md) is: illustrative drafts and requests, for
the maintainers to accept, reshape, or reject. It was written **after** reading
[`CONSTITUTION.md`](CONSTITUTION.md); every proposal below is framed to stay inside its invariants
(declarative-not-code, additive-within-a-major, orthogonal axes, the reserved namespace, the
vocabulary idiom). Where a proposal would touch `artifact.digest` bytes, it is flagged as
major-only, per Principle 3/4.

> ---
> ### ↳ maintainer annotations — pre-0.4 vitrification (round 1)
>
> This copy is **annotated inline**, mailing-list style. Blockquoted `↳ maintainer reply` blocks are
> the maintainer's condensed reasoning + decisions; the surrounding prose is the consumer's original
> text, unedited. Frozen column shapes and the open round-2 questions live in the companion
> [`PROPOSAL_0_4.md`](PROPOSAL_0_4.md) — this file is the discussion thread, that file is the spec draft.
> **Headline:** every ask is accepted in some form. Two diverge from the literal proposal (**B0**:
> shared column *vocabulary* across per-quantity tables, not one physical table; **B4**: an optional
> modifier *column*, not a tuple key), and **B5** goes *further* than our standing roadmap (we freeze
> the full `pgs.csv` now). A2 is already fixed on `main` (independently of this branch — a trivial
> comment fix shouldn't wait on the 0.4 discussion).
> ---

We are a production whole-genome pipeline (WGS + array-imputation) that has already built and
validated callers for most of what the format schedules for 0.4 and the *reserved namespace*:
PGx star-alleles (Aldy / Cyrius), short-read VNTR/STR genotyping (DAT1, DRD4, PER3, MAOA-uVNTR,
5-HTTLPR), mtDNA haplogroups + heteroplasmy, whole-gene CNV dosage (SMN1), HLA imputation (HIBAG),
and ancestry-aware PRS. The maintainers asked for **generalization from implementations**; that is
exactly the lens here — each proposal names the tool whose output it generalizes and gives a real
example row.

---

## TL;DR — one structural observation, then the requests

**The single most useful thing we can contribute is a generalization, not a pile of new tables.**
The format already contains the same declarative primitive *twice*:

- `activity_phenotype.csv` (PGx): `gene, score_min, score_max → phenotype`
- `copynumbers.csv` (item 7b): `gene, copy_number → direction/clin_sig/phenotype`

Both are **"a per-locus measured quantity, binned by range to a phenotype."** Every hard locus class
we have implemented reduces to that same shape, differing only in *which quantity* is measured:

| Locus class | Measured quantity | Our caller | Format status today |
|---|---|---|---|
| PGx metabolizer | activity score (Σ activity×copies) | Aldy, Cyrius | 0.4 (`activity_phenotype.csv`) |
| Whole-gene dosage | copy number | SMNCNC (SMN1) | 0.4 (`copynumbers.csv`, item 7b) |
| VNTR / STR | repeat count (per motif) | our span genotypers | reserved (`repeat_count`+`repeat_unit`) |
| mtDNA heteroplasmy | mutant allele fraction 0–1 | haplogrep3 + depth | reserved (`allele_fraction`) |
| Polygenic score | PRS percentile (ancestry-conditional) | PRS module | item 8, note-only |

So our headline request is **not** "add five bespoke tables." It is: **recognize the range→phenotype
binning as one first-class declarative primitive**, and let the four future quantity-carrying loci
(repeat count, heteroplasmy fraction, PRS percentile, plus the two that exist) reuse it. That keeps
the format small, stays purely declarative (a binning table is data, not code — Principle 1), and is
exactly the "schema from generalizing implementations" the maintainers asked for. Details in §B0.

> **↳ maintainer reply — TL;DR headline: accepted, with one shape decision.**
> - Yes: the range→phenotype binning is recognized as **one declarative primitive**. This is the
>   single most valuable contribution and it aligns with our own instinct (ROADMAP already says the
>   score→phenotype binning is "stored per gene as data, never hardcoded" and unifies items 7/7b/9).
> - **Not** one physical table, though — **one shared column vocabulary across per-quantity tables**
>   (you concede PRS is ancestry-conditional and the keys differ; forcing one table contorts the
>   frozen shape). Same consumer "bin-a-measure" code path, no schema contortion. See §B0 reply.
> - Timing is exactly right: 0.4 was held open for this. Nothing is frozen yet, so aligning the shapes
>   now is design-before-build, not migration.

The rest of this document is:

- **Part A — usability review** of the shipped 0.1–0.3 format from a consumer that has to *join*
  modules against real sample data. What we would adopt as-is, one code/docs inconsistency we found,
  and the one cross-cutting gap that bites *every* consumer regardless of module type
  (call-confidence).
- **Part B — grounded, additive proposals** for the reserved/0.4 loci, each generalized from a named
  caller with a real example row.

---

## Part A — usability review (shipped format, consumer's-eye)

### A1. What we would adopt directly, unchanged

These decisions match what we independently converged on in production; we would consume them with no
friction:

- **Integrity-as-identity (Merkle `artifact.digest`, `sha256:` everywhere).** We already treat our
  reference DBs as frozen, content-addressed inputs; a module whose identity *is* its content digest
  drops straight into a reproducible pipeline. Endorsed without reservation.
- **Declarative-not-code (Principle 1).** This is the correct line and we have paid for learning it:
  every attempt to smuggle interpretation logic into data becomes an un-auditable, un-reproducible
  liability. Lookup tables + a bounded predicate/regex escape hatch is the right envelope.
- **Orthogonal axes (Principle 5) and the `state`→`direction`/`stat_significance`/`clin_sig` split.**
  The overloaded `state` field is precisely the anti-pattern we hit; the 0.3 untangling is what we
  would have asked for. `clin_sig` as a proper tier (not two lossy booleans) is right.
- **`effect_allele` + `trait_efo_id` (0.3 item 5).** See A3 — this one is not just nice, it closes a
  class of silent bug we have been burned by. Strongly endorsed.
- **Inject-only, no-network (Principle 2).** Matches how we pin references. A compiler that *cannot*
  reach the network is a feature, not a limitation.
- **Genotype widening for hemizygous + phased (5b), and the MT/Y two-allele guardrail warning.** We
  hit exactly this trap (a "fake diploid" call on a haploid locus); a compiler that *warns* on a
  two-allele MT/Y genotype would have caught a real class of our early mistakes.

> **↳ maintainer reply — A1: endorsed, no action needed.** All six are shipped or intended-as-is; the
> MT/Y two-allele guardrail warning already lands in 0.3 item 5b (`compiler.py:267`). Noted as
> confirmation the axis-split direction was right.

### A2. One code/docs inconsistency (phase round-trip)

**Finding (low severity, but it touches a Principle-7 invariant).** The comment at
`compiler/src/just_dna_compiler/compiler.py:42-43` states that *"phase (the `|` vs `/` distinction)
is NOT preserved in the artifact — that is an intentionally-deferred computed item (see
docs/COMPILER.md)."* That is **stale and contradicts the shipped behavior and the cited doc**:

- The artifact *does* carry phase: `_build_weights` writes `"phased": "|" in v.genotype`
  (`compiler.py:559`), declared in the parquet schema (`compiler.py:592-593`).
- `reverse_module` uses it to re-emit `A|G` vs alphabetically-sorted `A/G`
  (`compiler.py:811-814`).
- `COMPILER.md` (the doc the comment points at) and `CONSTITUTION.md` Principle 7 both assert the
  **opposite** of the comment: phase survives the round-trip losslessly.

The comment is locally accurate about `_split_genotype`/`_GENOTYPE_SEP` (that *function* discards
phase), but the generalization "phase is not preserved in the artifact" is false — phase is preserved
*around* that function, by the `phased` column. A consumer implementer (us) reads this code to decide
whether phase can be trusted end-to-end; the comment says no, the contract says yes. **Suggested
fix:** reword to "`_split_genotype` discards the `|`/`/` distinction; phase is preserved separately
via the `phased` column (see `_build_weights`), so the round-trip is lossless (Principle 7)." Trivial,
but phase is load-bearing for us (parental phasing, cis/trans for compound-het, and the whole PGx
star-allele layer depends on it), so we want the code's self-description to match the guarantee.

> **↳ maintainer reply — A2: confirmed and fixed on `main`.** Verified against the current repo:
> the comment at `compiler.py:41-43` did contradict shipped behavior (`phased` is materialized at
> `_build_weights` line 559, declared in the parquet schema at 593, re-emitted in `reverse_module` at
> 806-812) and both `COMPILER.md` and Principle 7. Reworded exactly as you suggested — the function
> discards the `|`/`/` distinction, phase is preserved separately via the `phased` column, round-trip
> is lossless. Comment-only, no behavior change — landed straight on `main`, no version bump needed.
> Thanks for catching it; the code now says what the contract says.

### A3. Endorsing `effect_allele` — the strand/ref-flip silent bug is real

0.3 item 5 already adds `effect_allele` and names effect-allele/strand confusion "the #1 silent bug
here." We can confirm that from production, and add a second, sharper instance the note should call
out: **allele-orientation loss across a liftover.** When lifting an ALT-only representation from an
older build to GRCh38, sites where the reference base itself flipped between builds are silently
dropped or mis-oriented, and a downstream `weight`/`direction` then refers to the wrong allele with no
error anywhere. Our mitigations, offered as documentation the `effect_allele` note could adopt:

- **Always orient by an explicit anchor, never by position alone.** We re-derive orientation from an
  all-sites/callable reference and, where ambiguous, by allele frequency — because `ref`/`alts` + a
  `weight` sign is *not* enough to recover which allele the effect refers to.
- **Pin the reference sequence, not just the build.** `genome_build=GRCh38` is necessary but not
  sufficient for two locus classes: (a) **mtDNA**, where positions are meaningless without stating
  rCRS/NC_012920 vs the legacy NC_001807 — a mismatch we have seen produce a *confidently wrong*
  haplogroup (see §B3); and (b) indels near build-differing regions. We suggest the `effect_allele`
  documentation explicitly recommend recording the reference-sequence accession for MT loci, and that
  a future reserved `reference_sequence` note (analogous to `effect_allele` for strand) be added to
  the reserved namespace. This is the MT analog of the strand caveat and costs nothing until used.

> **↳ maintainer reply — A3: accept both.** (1) The `effect_allele` doc gains the liftover ref-flip
> caveat (orient by an explicit anchor, never position alone). (2) `reference_sequence` is reserved —
> the rCRS/`NC_012920` vs legacy `NC_001807` confidently-wrong-haplogroup hazard is a real one-way
> door and `genome_build=GRCh38` doesn't disambiguate it; it also becomes part of the `heteroplasmy.csv`
> key (see B3). **Open Q:** validated accession vocabulary vs free-form + a format-side warning on the
> known-dangerous legacy accessions? We lean the latter.

### A4. The cross-cutting gap that bites every consumer: call-confidence / callability

This is the one piece of feedback we would most want the maintainers to internalize, because it is
independent of module type and is *the* thing that turns a correct annotation into a wrong report.

**A module says "at rs1801133, T/T means reduced enzyme activity." To act on that, a consumer must
first answer a question the module cannot: is this sample confidently `T/T`, confidently hom-ref
`C/C`, or simply not called here (no coverage)?** These are three different truths, and the failure
mode is specific and common: a variant-only VCF has *no record* at a site, and a naive consumer reads
"no record" as "hom-reference." That is wrong. "No record" means *either* hom-ref (the site was
callable and matched the reference) *or* no-call (the site was never callable). Collapsing them
fabricates a confident reference genotype the data does not support — and for a recessive carrier
locus or a pathogenic-absence claim, that fabrication is exactly the dangerous direction.

We resolved this in our pipeline with an **all-sites / callable "oracle"**: every position is one of
`covered→hom-ref` (callable, matched reference) or `gap→NO_CALL` (never callable), and no annotation
is asserted against a `NO_CALL` site. The three-state genotype (variant / callable-hom-ref /
no-call) is load-bearing.

**This is legitimately a consumer concern, not a module field — and we are not asking the format to
carry per-sample coverage.** But two small, in-charter things would materially help every consumer:

1. **A normative note in the spec docs** — a "consumer join contract" — stating that a conforming
   consumer MUST distinguish covered-hom-ref from no-call before asserting a reference/absence
   interpretation, and MUST NOT treat "absent from a variant-only callset" as hom-ref. This is
   documentation, costs no schema, and encodes the single most expensive lesson we learned.
2. **An optional reserved flag, `requires_callable`** (row-level, on the open `flags` list or as a
   reserved boolean), marking rows where the *absence* of a variant is the informative call — i.e.
   where a no-call must degrade to "unknown," never to the reference conclusion. Recessive carrier
   screening and "pathogenic variant absent" reassurance are the motivating cases: there, silently
   reading no-call as reference is the difference between "screened negative" and "not screened." A
   module author flags such rows; a consumer that lacks callability data then knows to withhold the
   reassuring conclusion rather than assert it. Purely additive, opt-in, and it names a real hazard.

> **↳ maintainer reply — A4: accept both, this is the strongest conceptual contribution.**
> - (1) A normative **"consumer join contract"** note lands in the spec docs: a conforming consumer
>   MUST distinguish covered-hom-ref from no-call before asserting a reference/absence interpretation,
>   and MUST NOT read "absent from a variant-only callset" as hom-ref. Doc only, no schema.
> - (2) `requires_callable` is **reserved** for rows where the *absence* of a variant is the
>   informative call (recessive carrier, "pathogenic absent" reassurance) — a consumer lacking
>   callability then degrades to unknown, never the reassuring conclusion.
> - **Open Q:** reserved **flag** (fits the open `flags` list, zero schema change) vs a reserved
>   **typed boolean column** (queryable)? We lean flag for 0.4, promotable to a column later. Same
>   "unresolved ≠ reference" discipline as T1, one level down.

---

## Part B — grounded proposals (each generalized from a named caller)

Every subsection names the tool whose real output it generalizes, gives an actual column set / example
row, and states the proposed additive shape and its charter status. Three themes recur across all of
them, so we state them once here and then point back:

- **T1 — "unresolved" is a first-class value, never the reference bin.** Every caller we run has a
  *could-not-resolve* outcome that is recorded distinctly and must survive into the report as its own
  state: Cyrius emits `Genotype=None` + `METHOD_BLIND_SPOT` on 30× short-read CYP2D6; our PER3
  genotyper emits `CI` (insufficient spanning reads); the callable oracle emits `UNCOVERED(true
  no-call)`; the capability report has `LOW_CONFIDENCE`/`METHOD_BLIND_SPOT`/`NOT_ASSESSED`. The
  dangerous collapse is **unresolved → normal/reference** (no activity score ⇒ "Normal Metabolizer";
  no CN call ⇒ "2 copies"; no coverage ⇒ hom-ref). Any binning table (§B0) therefore needs an explicit
  unresolved outcome, and the consumer contract (§A4) needs the not-callable state.
- **T2 — a computed call carries caller provenance.** A diplotype / CN / repeat call is a *computed*
  quantity, not a raw genotype; which tool + version + reference produced it is load-bearing (Aldy's
  header pins `pharmvar-6.2.14`; SMNCopyNumberCaller and Cyrius pin their versions). We record a
  `caller, caller_version, reference_db` triple on every computed call.
- **T3 — a measured count is only comparable within its unit definition.** Two VNTR callers gave
  DAT1 `21/41` vs `3/3` for the *same* sample — different motif definitions, not a discordance. A
  repeat/CN/score count without its unit definition (motif, panel, reference) is meaningless, so the
  definition must be part of the value's identity.

> **↳ maintainer reply — T1/T2/T3: all three accepted as cross-cutting invariants.** These matter more
> than any single table.
> - **T1 (unresolved is first-class, never the reference bin)** — baked into the binning primitive as a
>   mandatory `unresolved` outcome + consumer contract (§B0). This is the load-bearing safety property.
> - **T2 (a computed call carries caller provenance)** — we **reserve** `caller` / `caller_version` /
>   `reference_db` so any table carrying a *computed* call (diplotype/CN/repeat/heteroplasmy) can adopt
>   them additively, and a consumer-side call can label provenance in a shape we recognize. Not required
>   in 0.4 (format supplies tables, consumer supplies the call). **Open Q:** three columns vs one
>   composite string — your Aldy/Cyrius/SMNCopyNumberCaller headers pin all three separately, which
>   argues for three.
> - **T3 (a count is comparable only within its unit definition)** — the unit is part of the phenotype
>   *key*: `(gene, repeat_unit)` for repeats (§B2), `(gene, reference_sequence)` for heteroplasmy (§B3),
>   `training_ancestry` population axis for PRS (§B5). A bare count with no unit is rejected by shape.

### B0. The unifying primitive — `measure → phenotype` binning (one shape, five quantities)

The format already ships this shape twice (`activity_phenotype.csv`, `copynumbers.csv`). We propose
recognizing it as **one declarative primitive**: a per-locus table that bins a consumer-supplied
*measured quantity* into a phenotype by range. Parameterizing it by the quantity covers every hard
locus class we implement:

```
# generic binning table: <locus-key>, <measure> range → the same axis columns a VariantRow carries
gene, measure_kind, measure_min, measure_max, direction, clin_sig, phenotype, trait_efo_id, conclusion
```

- `measure_kind ∈ {activity_score, copy_number, repeat_count, allele_fraction, prs_percentile}` — an
  open, additive vocabulary (the `frozenset[str]` idiom, Principle 6).
- **Division of labor is identical to the 0.4 star-allele gate**: the format supplies the binning
  *table* (declarative data); a **consumer** supplies the *measurement* (activity score from a PGx
  caller, CN from a CNV caller, repeat count from a repeat genotyper, heteroplasmy fraction, PRS
  percentile) *and its confidence*. Nothing here is code.
- **Reserve an explicit `unresolved` outcome (T1).** A binning table must be able to say "measurement
  absent / not callable ⇒ this locus is *unresolved*, not normal." Concretely: the consumer contract
  is that a missing measurement selects an `unresolved` result, never the lowest/reference bin.

Why this matters for the one-way door: `activity_phenotype.csv` and `copynumbers.csv` are about to
freeze their column names. If they freeze as *bespoke* tables, the future `repeat_count` /
`allele_fraction` / `prs_percentile` loci each get *another* bespoke table, and the four never share a
consumer code path. Unifying now (or at least aligning their column names — `*_min`/`*_max`/`phenotype`
/`direction`/`clin_sig`/`trait_efo_id`) means one consumer "bin a measure" implementation serves all
five. This is the concrete "schema from generalizing implementations" ask.

*(PRS is the partial exception: its binning is ancestry-conditional — see §B5 — so its table is
parameterized by population. That is an argument for treating the binning table generically enough to
carry an optional parameter axis, not for a separate table.)*

> **↳ maintainer reply — B0: accept the primitive; shared column *vocabulary*, per-quantity tables.**
> - We freeze one column vocabulary every binning table carries:
>   `<key…>, measure_kind, measure_min, measure_max, direction, clin_sig, phenotype, trait_efo_id, conclusion, unresolved`,
>   with `measure_kind ∈ {activity_score, copy_number, repeat_count, allele_fraction, prs_percentile}`
>   (open `frozenset`). Keys vary per quantity (see the per-table replies).
> - **Not a single physical `measure_bins.csv`** — you name the reason yourself (PRS is
>   ancestry-conditional; keys differ). Aligned columns give the single "bin-a-measure" consumer path;
>   one table would contort the frozen shape. This is the one place we take the idea but not the literal form.
> - **T1 baked in:** `unresolved` is a *mandatory* outcome, and the consumer contract is that a missing
>   measurement selects `unresolved`, **never the lowest/reference bin.** This is non-negotiable and
>   sits in the primitive, not per-table.
> - **Open Qs:** half-open `[min,max)` vs inclusive bounds? `unresolved` as a sentinel row vs an enum
>   the consumer resolves to when no bin matches? (We lean half-open + sentinel row — confirm against
>   how your callers emit `METHOD_BLIND_SPOT`/`CI`/`NO_CALL`.)

### B1. PGx star-alleles — validating the 0.4 four-table model against Aldy / Cyrius / PharmCAT

The 0.4 design (star-string as canonical identity; `allele_function.csv`; per-gene
`activity_phenotype.csv`; `diplotypes.csv` as the structural/unphased fallback; CN as an attribute of
a *cis* allele-unit) is **correct** — it matches our three-caller stack exactly. Grounding:

- **Aldy** (`samples/<s>/14_aldy/CYP2D6.aldy`) — columns `Sample Gene SolutionID Major Minor Copy
  Allele Location Type Coverage Effect dbSNP Code Status`, with the gene-level activity/phenotype in a
  header comment: `#Solution 1: *1.001, *1.012; gene=CYP2D6-pharmvar-6.2.14; cpic=normal;
  cpic_score=2.0`. So `Major` = the star diplotype (`*1/*1`), `Minor` = suballeles (`1.001;1.012`),
  and the **activity score (`cpic_score=2.0`) + phenotype (`normal`)** are the binning output.
- **Cyrius** (structural CYP2D6, JSON) — `Total_CN, Spacer_CN, Exon9_CN, CNV_consensus, Genotype,
  Filter, Raw_star_allele`. This is precisely "CN as a property of the allele-unit": `Total_CN` /
  `Spacer_CN` / `Exon9_CN` decompose the duplication/hybrid structure the star-string names.
- **Integrated passport** (`13_cardiometabolic/cad_pgx.tsv`) — `gene, variant_or_diplotype, source,
  genotype, function_status, phenotype, direction, drug_context, tier, prescription_conditional,
  note` — one row carrying diplotype + activity + phenotype + direction, exactly the join the format's
  four tables produce.

Three additive refinements from running this in production:

1. **First-class unresolved (T1).** On 30× short-read, Cyrius returns `Genotype=None` for CYP2D6
   (paralog/structural limit) and we record `METHOD_BLIND_SPOT`, *never* "Normal Metabolizer." The
   `activity_phenotype.csv` binning must therefore have an explicit unresolved outcome (§B0), and the
   consumer contract must forbid "no diplotype ⇒ normal." This is the single most important safety
   property of the whole PGx layer.
2. **Caller provenance triple (T2).** The phenotype passport records `source=Aldy(structural)` and
   pins `pharmvar-6.2.14`; PharmCAT and Cyrius carry their own versions. A consumer that ingests a
   diplotype *call* (not the format's tables, but the sample-side call it matches) benefits from a
   `caller / caller_version / reference_db` convention. Suggest reserving those names.
3. **Suballele granularity is optional-extra, not core.** Aldy's `Minor` (`1.001;1.012`) is finer than
   the core star (`*1`). The format is right that the **core** star-string is the identity; we would
   add only that `allele_function.csv` may optionally carry a suballele column for callers that report
   it, with the core star as the required key.

> **↳ maintainer reply — B1: four-table model endorsed; all three refinements accepted.**
> - The star-string-verbatim-as-identity design stands (SVs live in the name; `sv_type`/`copy_number`/
>   `hybrid_orientation` are optional parsed conveniences). Your three-caller stack confirms it.
> - (1) **First-class unresolved** — via the shared binning `unresolved` outcome (§B0). `Genotype=None`
>   on 30× short-read ⇒ `unresolved`, never "Normal Metabolizer".
> - (2) **Caller provenance** — via the reserved T2 triple (see the T2 note below).
> - (3) **Optional suballele column** on `allele_function.csv`, with the **core star as the required
>   key**. Suballele is optional-extra, not identity — agreed.
> - **Open Q:** confirm tandems/hybrids (`*36+*10`, `*68+*4`) arrive from Aldy/Cyrius as verbatim
>   star-strings, so we don't over-structure the SV field.

### B2. VNTR / STR repeats — promote the reserved `repeat_count` + `repeat_unit` with a concrete shape

The reserved namespace already lists `repeat_count` + `repeat_unit`; the ROADMAP notes "a sequence
regex can't express '42 CAG'." We have production genotypers for this and can offer the concrete shape.

- **Our span genotyper** (`scripts/per3_span_genotyper.py` → `graph/PER3_SPAN_GENOTYPE.tsv`) — columns
  `sample, n_reads, 4R_span, bbb_5R, unresolved2b, bc_dosage, G_VAF, haplotype, call, tier`. Allele =
  `call` (`4R/4R`, `4R/5R`, `CI`); evidence = spanning-read counts; `tier` = a PROXY/short-read caveat.
- **adVNTR** (orthogonal caller) — `locus, advntr_R1, advntr_R2, spanning, flanking, confidence`
  (`MAOA_uVNTR 5 5 104 . high`). `R1/R2` = per-allele repeat counts; `confidence ∈ {high, nocall,
  not-modeled}`.
- **DAT1** is recorded as a **motif path**, not a bare count: `10R = A-A-B-C-D-E-F-D-G-H (405bp)`,
  motif `F = 45bp` — because the discriminating signal is the motif composition, not an integer.

Proposal — a binning table `repeat_alleles.csv` (an instance of §B0), plus two hard constraints our
data forces:

```csv
gene, repeat_unit, min_count, max_count, direction, clin_sig, phenotype, trait_efo_id, conclusion
HTT,  CAG,        40,        ,          risk,      pathogenic, "Huntington disease (full penetrance)", MONDO_0007739, "≥40 CAG — fully penetrant"
HTT,  CAG,        36,        39,        risk,      pathogenic, "Huntington disease (reduced penetrance)", MONDO_0007739, "36–39 CAG — reduced penetrance"
HTT,  CAG,        27,        35,        neutral,   uncertain_significance, "Intermediate allele", MONDO_0007739, "27–35 CAG — intermediate, not affected"
```

- **`repeat_unit` (motif) is mandatory and part of the phenotype key (T3).** Two of our callers gave
  DAT1 `21/41` vs `3/3` on the same sample — same locus, *different motif definitions*, so the counts
  are non-comparable and reconcile only qualitatively. A bare `repeat_count` with no motif is
  meaningless; key repeat phenotypes on `(gene, repeat_unit)`, and require the consumer's repeat call
  to state the motif it counted.
- **Short-read callability caveat (T1).** A repeat count is frequently `CI`/insufficient-spanning on
  short reads; the binning table needs the unresolved outcome, and the count is a *consumer* call
  (ExpansionHunter / adVNTR / a span genotyper), never authored.
- **Optional, for complex VNTRs:** the motif-path form (DAT1 `A-A-B-C-D-…`) is exactly the kind of
  string the Constitution's sanctioned **declarative-grammar escape hatch** (a regex over an allele
  string, Principle 1) was reserved for — if a plain count proves too coarse. We flag this as the
  natural home for that escape hatch, not as a near-term ask.

> **↳ maintainer reply — B2: accept `repeat_alleles.csv` keyed on `(gene, repeat_unit)`.**
> - The motif is part of the identity (T3). Your DAT1 `21/41` vs `3/3` case (same sample, different
>   motif definitions) is exactly why a bare `repeat_count` is non-comparable — so the consumer's
>   repeat call MUST state the motif it counted, and the count is a consumer call
>   (ExpansionHunter/adVNTR/span genotyper), never authored. Frozen shape is in `PROPOSAL_0_4.md`.
> - Short-read `CI`/insufficient-spanning maps to the `unresolved` outcome (T1).
> - The complex-VNTR **motif-path** form (DAT1 `A-A-B-C-D-…`) is reserved as the home for the
>   sanctioned declarative-grammar escape hatch (regex over an allele string) — **not built now**.
> - **Open Q:** `repeat_unit` free-form motif string vs constrained ACGT/IUPAC pattern (so the format
>   can validate it)? And how do you want 5-HTTLPR short/long handled — motif count or a named allele?

### B3. mtDNA — homoplasmy (already reachable) + heteroplasmy fraction (reserved) + reference-sequence pin

- **Heteroplasmy** (`samples/<s>/mtdna/heteroplasmy_summary.tsv`) — `pos, ref>alt, heteroplasmy_AF,
  DP, filter, note`; e.g. `8911 T>C 0.107 1916 PASS "genuine low-level heteroplasmy ~11%"`, alongside
  a `NOT_CALLED` row that records a rejected caller artifact (T1 again). So the reserved
  `allele_fraction` maps directly to `heteroplasmy_AF` (0–1), and a penetrance-threshold **binning
  table** (fraction range → phenotype, an instance of §B0) is the phenotype layer. Homoplasmic calls
  are already reachable via the 5b single-allele genotype.
- **Reference-sequence pin (ties to §A3).** Our worst mtDNA failure mode is not the fraction — it is
  the reference. Processing MT reads against the legacy **NC_001807** (rather than rCRS / **NC_012920**)
  yields a *confidently wrong* haplogroup (the rCRS's own H2a2a1 lineage) because the coordinates and
  reference bases silently disagree. `genome_build=GRCh38` does not disambiguate this. We recommend a
  reserved `reference_sequence` note for MT loci (record the accession), as the MT analog of the
  `effect_allele` strand caveat.
- **Haplogroup as a named haplotype.** A haplogroup (haplogrep3: `H5a1j`, quality `0.896`) is a named
  set of MT variants — structurally the same as an APOE ε-haplotype, but single-copy. It fits the item-7
  haplotype table with a single allele slot; the `Quality`/`Rank` fields are a caller-confidence axis
  (T2).

> **↳ maintainer reply — B3: accept `heteroplasmy.csv` as an `allele_fraction` binning table.**
> - Keyed on `(gene, reference_sequence)` per A3; `heteroplasmy_AF` (0–1) maps straight in. Homoplasmic
>   calls stay reachable via the 0.3 item-5b single-allele genotype; the haplogroup fits the item-7
>   haplotype table with `Quality`/`Rank` as the T2 confidence axis; the `NOT_CALLED` rejected-artifact
>   row maps to `unresolved` (T1).
> - **Open Q:** heteroplasmy penetrance thresholds are tissue-dependent (blood vs affected tissue).
>   `tissue`/`assay_context` in-format or consumer-side? We lean consumer-side but flag it because it
>   changes what the phenotype *means*.

### B4. CNV dosage — item 7b is right, but SMN needs a compound key

`copynumbers.csv` (item 7b) matches SMNCopyNumberCaller's output — but the SMN example the ROADMAP
uses to motivate item 7b is exactly the case the *simple* shape can't fully express.

- **SMNCopyNumberCaller** (`samples/<s>/09_cnv/smn/*_smn.tsv`) — `Sample, isSMA, isCarrier, SMN1_CN,
  SMN2_CN, SMN2delta7-8_CN, Total_CN_raw, Full_length_CN_raw, g.27134T>G_CN, SMN1_CN_raw`. Example:
  `False False 2 2 0 4.319 3.847 …` (normal) and a carrier `False True 1 0 …`.
- **The refinement: SMA phenotype is a function of `SMN1_CN` *and* `SMN2_CN`.** `SMN2_CN` is a
  well-established dosage modifier — 0 SMN1 copies with 3–4 SMN2 copies is a milder phenotype than 0
  SMN1 / 1 SMN2. The pure `gene, copy_number → phenotype` row cannot say this. We suggest the binning
  table admit an **optional modifier term** (a second `(gene, copy_number)` in the key), so SMN1 dosage
  can be read in the context of SMN2 dosage. Generic phrasing: the binning key may be a small tuple of
  `(gene, copy_number)` pairs, not always a single gene.
- Plus the recurring pair: **caller provenance (T2)** (`SMNCopyNumberCaller v1.1.2`) and the
  **unresolved state (T1)** — in a segmental-duplication region at ~20×, CN is often *not resolved*
  (`Total_CN_raw=1.34 → копийность не разрешена; нужен MLPA`), recorded as `METHOD_BLIND_SPOT`, never
  as a confident "2 copies."

> **↳ maintainer reply — B4: accept the SMN2 modifier — as an optional *column*, not a tuple key.**
> - The clinical point is right (SMN2 is an established SMA dosage modifier), and the row genuinely
>   needs a compound key. But a compound key in a relational/CSV contract is spelled with **explicit
>   named columns (multicolumn keying), never a packed `(gene, cn)` tuple** — a tuple-as-key is opaque
>   to a CSV reader, unqueryable per-component, order-fragile: a coder shortcut, not a protocol idiom.
>   (Coding-standards call, not a Constitution one — but firm: keys here are always named columns.) So
>   `copynumbers.csv` keeps its scalar `gene` key and gains an **optional, nullable `modifier_gene` +
>   `modifier_cn` pair**. Single-gene rows leave them null. Shape + example rows in `PROPOSAL_0_4.md`.
> - Plus the recurring pair: caller provenance (T2, `SMNCopyNumberCaller v1.1.2`) and unresolved (T1 —
>   a seg-dup region at ~20× is often not resolved: `METHOD_BLIND_SPOT`, never "2 copies").
> - **Open Q (gates the freeze):** is a **single** modifier pair enough for every dosage locus you run?
>   If one covers all real cases we freeze exactly one pair. If a locus ever needs two-plus modifiers,
>   the answer is a second named pair (or a small `dosage_modifiers` side table) — **not** a tuple key;
>   the stance above holds.

### B5. Ancestry-conditional PRS — the ask to settle *before* item 8's shape freezes

This is our strongest scientific-correctness contribution, and it is time-sensitive because item 8
(`pgs.csv`) is note-only *now* — the one moment its permanent shape can absorb this without a later
migration.

- **Our PRS output** (`samples/<s>/03_prs/prs_results.tsv`) — `PGS, Trait, N_match, SUM, EUR_mean,
  EUR_sd, Z, pctl`; e.g. `PGS000135 SCZ 972068 15.02 10.85 1.474 +2.83 99.8%`. The ancestry frame is
  *structural* — the mean/sd/percentile are all EUR-referenced.
- **Cross-population calibration** (`10_prs/cross_pop/cross_population_results.json`) — per-population
  `{mean, sd, n, z}`, where the EAS/AFR z of ≈ −8 are *mandated negative controls* proving the
  ancestry-scale mismatch when a EUR-trained score is applied out of population.

The gap (confirmed absent from our own disk as a structured field, and present only in our *rule
text*): there is **no per-PGS ancestry-validity column** — and item 8, as sketched, has none either.
We propose the `pgs.csv` shape carry, from day one:

- **`training_ancestry`** (the population(s) the score was derived/validated in) — our scoring rule
  already mandates this in a score's metadata; make it a column so a consumer can *refuse or caveat*
  an out-of-ancestry application instead of silently miscalibrating.
- **`match_rate` floor** — a hard rule we enforce: **> ~20% variant mismatch invalidates the score.**
  A consumer needs the floor to reject a score computed on too few matched variants.
- **A `research_tier` marker** — a PRS yields a Z / percentile *within a matched reference
  distribution*, **never an ancestry-calibrated absolute risk**, and `|Z| ≥ 2.5` in a *healthy*
  proband is a **population-stratification signal, not a disease prediction.** Pinning this as data
  (not just consumer lore) is what keeps a downstream UI from rendering a EUR-frame percentile as a
  personal risk for a non-EUR sample.

This is not only correctness hygiene; it is the anti-misuse guardrail for the highest-stakes module
type. Settling `training_ancestry` + `match_rate` + `research_tier` before the shape freezes avoids
the exact silent-miscalibration failure the `effect_allele`/strand work was added to prevent — the
same class of one-way-door bug, one level up.

> **↳ maintainer reply — B5: accept, and we go *further* than our standing roadmap — freeze the full
> `pgs.csv` this run.**
> - Our roadmap kept item 8 note-only because just-prs has no combine-into-one-score primitive, so
>   per-PGS *weights* would be dead data. That reasoning holds for weights — but your three anti-misuse
>   fields are a one-way door independent of the combine question, on the highest-stakes module type. So
>   we freeze: `pgs_id, trait_efo_id, note, group, training_ancestry, match_rate, research_tier`
>   (+ optional header `quality_floor`). Full shape in `PROPOSAL_0_4.md`.
> - `training_ancestry` is the ancestry parameter axis the binning primitive (§B0) left room for;
>   `research_tier` pins as *data* that a PRS is a Z/percentile-in-reference, never an ancestry-calibrated
>   absolute risk.
> - **Open Qs (these gate the freeze):** `training_ancestry` — 1000G superpop codes (`EUR/EAS/AFR/AMR/SAS`,
>   open `frozenset`, list-valued for multi-ancestry) vs free string? `match_rate` — store the author's
>   *floor*, the consumer's *observed* rate at scoring time, or **both** (different fields — name both now
>   or split later)? `research_tier` — boolean vs open vocabulary so a future calibrated score can declare
>   itself?

### B6. Actionability / return-tier — raised carefully, deferring to the non-goal

The Constitution's non-goal is clear: interpretation and *presentation* belong to consumers, and the
format does no gene–disease inference. We agree, and we are **not** asking the format to make
disclosure decisions. But there is a clean data/policy seam worth naming:

- The **consumer's disclosure policy** — whether/how to return a result to a person — is correctly
  out of scope. In our pipeline this is a structured `disclosure_class` field
  (`GATED_OPT_IN` for incurable/untreatable late-onset findings vs `INFORMED_DISCLOSE` for
  actionable/modifiable ones; a *confirmed-negative* in the gated class is disclosable). That is *our*
  policy layer and stays consumer-side.
- But the **actionability / modifiability of the finding itself** — is the condition treatable,
  preventable, pharmacogenomically actionable, or incurable? is it on the ACMG secondary-findings
  list? — is a property of the gene–condition–intervention triad, i.e. *annotation-level data*, not
  presentation. It is the input a consumer's disclosure policy keys on.

So the (note-only, for-discussion) suggestion is a reserved `actionability` axis — an open vocabulary
like `{actionable, preventable, pharmacogenomic, incurable, reproductive}` — that a module *may*
carry and a consumer's return-of-results policy *may* read, without the format itself deciding
disclosure. This keeps the boundary the Constitution draws intact (data in the format, policy in the
consumer) while giving the policy something structured to stand on. We raise it only to reserve the
name against the one-way door; whether it belongs at all is the maintainers' call.

> **↳ maintainer reply — B6: accept as a reserved, note-only axis.** The seam you draw is the right one:
> annotation-level **actionability** (treatable/preventable/pharmacogenomic/incurable/reproductive; ACMG-SF
> membership) is a property of the gene–condition–intervention triad = *data*; the consumer's
> **disclosure policy** (whether/how to return a result to a person) stays consumer-side. We **reserve**
> `actionability` as an open vocabulary a module *may* carry and a return-of-results policy *may* read —
> the format never decides disclosure. This keeps the Constitution boundary intact.
> - **Open Q:** confirm the seed vocabulary `{actionable, preventable, pharmacogenomic, incurable,
>   reproductive}`, and whether ACMG-SF membership is a *value* in this axis or a separate reserved flag
>   `acmg_sf`. We lean separate flag — ACMG-SF is a list-membership fact, actionability is a category.

---

## Summary of asks (by charter cost)

| # | Ask | Charter status | Cost |
|---|---|---|---|
| A2 | Fix the stale phase-round-trip comment in `compiler.py:42-43` | docs/code only | trivial |
| A3 | `effect_allele` docs: add the liftover ref-flip caveat; reserve `reference_sequence` for MT | additive / reserved-namespace note | trivial |
| A4 | Spec "consumer join contract" note: no-call ≠ hom-ref; optional reserved `requires_callable` flag | doc + one reserved flag | low |
| B0 | Recognize `measure → phenotype` binning as one primitive; align `activity_phenotype`/`copynumbers` column names; reserve an `unresolved` outcome | additive; shapes align *before* 0.4 freeze | low, time-sensitive |
| B1 | PGx four-table model: endorsed; add first-class unresolved + `caller/caller_version/reference_db` + optional suballele | additive on 0.4 | medium (0.4) |
| B2 | Promote `repeat_count`+`repeat_unit` as a §B0 binning table keyed on `(gene, repeat_unit)`; motif is identity | additive; reserved → built | medium |
| B3 | `allele_fraction` heteroplasmy as a §B0 fraction-binning table; reserve `reference_sequence` for MT | additive / reserved | medium |
| B4 | `copynumbers.csv`: allow an optional modifier term (SMN1 read in context of SMN2) + caller provenance + unresolved | additive on 0.4 (item 7b) | low |
| B5 | **item 8 `pgs.csv`: pin `training_ancestry` + `match_rate` floor + `research_tier` before the shape freezes** | additive; one-way-door, **time-sensitive** | low, do-now |
| B6 | Reserve a note-only `actionability` axis (data), distinct from the consumer's disclosure policy | reserved-namespace note | trivial |

The two we would prioritize because they are one-way doors closing soon: **B5** (ancestry validity on
the PGS shape) and **B0** (aligning the two existing binning tables before four more quantities inherit
their divergence). Everything else is additive and can land whenever it is convenient.

> ---
> ### ↳ maintainer disposition (round 1) — all ten accepted
>
> | # | Verdict | Freezes in |
> |---|---|---|
> | A2 | **Done** (comment fixed) | landed on `main` |
> | A3 | Accept — liftover caveat + reserve `reference_sequence` | reserved namespace |
> | A4 | Accept — consumer-join-contract note + reserve `requires_callable` | doc + reserved flag |
> | B0 | Accept — shared column vocabulary, per-quantity tables (not one physical table); `unresolved` mandatory | 0.4 |
> | B1 | Accept — four-table model + unresolved + provenance triple + optional suballele | 0.4 |
> | B2 | Accept — `repeat_alleles.csv` keyed `(gene, repeat_unit)` | 0.4 |
> | B3 | Accept — `heteroplasmy.csv` (`allele_fraction`) keyed `(gene, reference_sequence)` | 0.4 |
> | B4 | Accept — optional `modifier_gene`/`modifier_cn` column (not a tuple key) | 0.4 |
> | B5 | Accept — **freeze full `pgs.csv` now**, further than our roadmap | 0.4 |
> | B6 | Accept — reserve note-only `actionability` axis | reserved namespace |
>
> Two divergences from the literal proposals (B0 shape, B4 modifier form) and one over-delivery (B5).
> The frozen column shapes are drafted in [`PROPOSAL_0_4.md`](PROPOSAL_0_4.md); its round-2 checklist
> collects the nine open questions inlined above. **Nothing is vitrified until those are answered** —
> 0.4 stays open for one more pass. Thanks for grounding every ask in a named caller and a real row;
> that is exactly the "schema from generalizing implementations" we asked for.
