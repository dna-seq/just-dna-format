# Pre-0.4 contract vitrification — maintainer response to the field notes

**Status: proposal / round-1 response — nothing here is shipped.** This document answers
[`CONSUMER_FIELD_NOTES.md`](CONSUMER_FIELD_NOTES.md) ask-by-ask and pins the shapes we intend to
**freeze in 0.4**. 0.4 was deliberately held open for this feedback before vitrifying the relational
contracts (items 7 / 7b / 8 and the reserved namespace), so this is the moment those shapes settle.
It is written to be sent back to the consumer for a second round — each accepted item ends with the
**open questions** we still want their production data to answer before the bytes freeze.

Everything below stays inside the Constitution (declarative-not-code, additive-within-a-major,
orthogonal axes, reserved namespace, the `frozenset[str]` vocabulary idiom). New CSV tables
materialize into new parquet files, which *are* `artifact.digest` bytes — that is legal here only
because **0.4 is unpublished, so the digest is not yet frozen** (CONSTITUTION Principle 3/4). Once
0.4 ships, every column below is major-only.

---

## Verdicts at a glance

| # | Ask | Verdict | Freezes in |
|---|---|---|---|
| A2 | Stale phase-round-trip comment | **Done** (code) | landed on `main` (independent of this branch) |
| A3 | Liftover ref-flip caveat; reserve `reference_sequence` for MT | **Accept** | reserved namespace |
| A4 | Consumer join contract (no-call ≠ hom-ref); reserve `requires_callable` | **Accept** | doc + reserved flag |
| B0 | `measure → phenotype` binning as one primitive | **Accept — shared column vocabulary, per-quantity tables** | 0.4 |
| T1 | "unresolved" is first-class, never the reference bin | **Accept — mandatory `unresolved` outcome on every binning table** | 0.4 |
| T2 | Caller provenance triple | **Accept — reserve `caller` / `caller_version` / `reference_db`** | reserved namespace |
| T3 | A measured count is comparable only within its unit definition | **Accept — unit is part of the phenotype key** | 0.4 |
| B1 | PGx four-table model + unresolved + provenance + optional suballele | **Accept** | 0.4 |
| B2 | `repeat_alleles.csv` keyed on `(gene, repeat_unit)` | **Accept** | 0.4 |
| B3 | `heteroplasmy.csv` (`allele_fraction` binning) + `reference_sequence` | **Accept** | 0.4 |
| B4 | SMN1-in-context-of-SMN2 dosage modifier | **Accept — optional `modifier_gene`/`modifier_cn` column, not a tuple key** | 0.4 |
| B5 | `pgs.csv`: `training_ancestry` + `match_rate` + `research_tier` | **Accept — freeze the full shape now** | 0.4 |
| B6 | Reserve note-only `actionability` axis | **Accept** | reserved namespace |

Two decisions diverge from the notes' literal proposal and are called out where they occur: **B0**
(shared column *vocabulary* across per-quantity tables, not one physical table) and **B4** (an
optional modifier *column*, not a tuple key). **B5** goes *further* than the standing roadmap
(which kept item 8 note-only): we freeze the full `pgs.csv` this run because the anti-misuse fields
are a one-way door and worth pinning even ahead of a just-prs collection consumer.

---

## A2 — phase round-trip comment (done)

Fixed on `main` directly (commit landed independently of this branch — a trivial comment fix should
not wait on the 0.4 discussion). `_GENOTYPE_SEP`'s comment now states that the function discards the
`|`/`/` distinction but phase is preserved separately via the `phased` column (materialized in
`_build_weights`, re-emitted in `reverse_module`), so the round-trip is lossless — matching
`COMPILER.md` and Constitution Principle 7. Comment-only, no behavior change, so no version bump /
release: it rides along in the next shipped version.

---

## The shared binning vocabulary (B0 + T1 + T3)

The headline generalization is accepted, with one shape decision: **per-quantity tables that share
one column vocabulary and one consumer contract**, *not* a single physical `measure_bins.csv`. The
notes themselves concede PRS is ancestry-conditional and the natural keys differ per quantity;
forcing one table would contort the frozen shape. Aligning the columns gets the single
"bin-a-measure" consumer code path — the actual win — without that cost.

**Frozen column vocabulary** (every binning table carries these; the *key* columns vary):

```
<key…>, measure_kind, measure_min, measure_max,
direction, clin_sig, phenotype, trait_efo_id, conclusion, unresolved
```

- `measure_kind ∈ {activity_score, copy_number, repeat_count, allele_fraction, prs_percentile}` —
  open, additive `frozenset[str]` (Principle 6).
- `measure_min` / `measure_max` — half-open range `[min, max)`; either bound nullable for
  open-ended bins (`≥40 CAG` = `min=40, max=null`).
- `direction` / `clin_sig` / `trait_efo_id` — the same orthogonal axes a `VariantRow` carries.
- **`unresolved` (T1) is mandatory.** A binning table MUST be able to state the outcome for
  *measurement absent / not callable*, and the **consumer contract is: a missing measurement selects
  the `unresolved` result, never the lowest/reference bin.** No activity score ⇒ not "Normal
  Metabolizer"; no CN call ⇒ not "2 copies"; no heteroplasmy read ⇒ not "homoplasmic reference".
  This is the single most important safety property of the whole quantitative layer and it is baked
  into the primitive, not left to each table.

**Keying stance (applies to every table below).** Keys are always **explicit, named columns**
(multicolumn keying), never a packed tuple. When a phenotype depends on more than one quantity
(repeat motif, reference sequence, a dosage modifier, an ancestry axis), each component is its own
column — legible to a CSV reader, queryable per-component, order-independent. A `(gene, count)` tuple
crammed into one key cell is a coder reflex, not a protocol design; it is rejected on coding-standards
grounds (not a Constitution invariant, but firm). This is why B4's modifier is two columns, not a tuple.

**Per-quantity keys (T3 — the unit is part of the key, as explicit columns):**

| Table | `measure_kind` | Key |
|---|---|---|
| `activity_phenotype.csv` | `activity_score` | `gene` |
| `copynumbers.csv` (7b) | `copy_number` | `gene` (+ optional modifier, see B4) |
| `repeat_alleles.csv` | `repeat_count` | `gene, repeat_unit` |
| `heteroplasmy.csv` | `allele_fraction` | `gene` (+ `reference_sequence`, see B3) |
| `pgs.csv` (item 8) | `prs_percentile` | `pgs_id` (+ `training_ancestry` population axis, see B5) |

**Open questions to the consumer:**

- Is `[min, max)` half-open the convention your callers expect, or do you bin inclusively on both
  ends? (HTT `36–39` vs `≥40` boundary handling is the concrete case.)
- Do you want `unresolved` as a **boolean flag on a sentinel row** (one row per table marked
  `unresolved=true`, no range) or as an **enum value the consumer resolves to** when no bin matches?
  We lean sentinel-row; confirm against how your callers emit `METHOD_BLIND_SPOT` / `CI` / `NO_CALL`.

---

## T2 — caller provenance triple (reserved)

Accepted as a **reserved-namespace convention**, not new required columns. A diplotype / CN / repeat
/ heteroplasmy call is a *computed* quantity; which tool produced it is load-bearing. We reserve the
names `caller`, `caller_version`, `reference_db` so any table carrying a computed call can adopt them
additively, and so a consumer-side call can label its provenance in a shape the format recognizes.
Not required in 0.4 (the format supplies the *tables*; the consumer supplies the *call*), but
reserved against the one-way door.

**Open question:** should the triple be one composite string (`aldy@6.2.14/pharmvar-6.2.14`) or three
columns? Three is more queryable; your Aldy/Cyrius/SMNCopyNumberCaller headers pin all three
separately, which argues for three.

---

## A3 / B3 — reference-sequence pin (reserved)

Accepted. Two parts:

1. **`effect_allele` doc gains the liftover ref-flip caveat** — orient by an explicit anchor, never
   position alone; a `ref`/`alts` + `weight` sign is not enough to recover which allele an effect
   refers to across a build lift. (Documentation only.)
2. **Reserve `reference_sequence`** for MT (and indels near build-differing regions) — the rCRS /
   `NC_012920` vs legacy `NC_001807` hazard produces a *confidently wrong* haplogroup, and
   `genome_build=GRCh38` does not disambiguate it. This is the MT analog of the strand caveat. For
   `heteroplasmy.csv` (B3), `reference_sequence` is part of the key.

**Open question:** do you want `reference_sequence` as an accession string (`NC_012920.1`) validated
against a small reserved vocabulary, or free-form with a format-side warning on the known-dangerous
legacy accessions?

---

## A4 — consumer join contract + `requires_callable` (reserved)

Accepted, both parts:

1. **A normative "consumer join contract" note** in the spec docs: a conforming consumer MUST
   distinguish covered-hom-ref from no-call before asserting a reference/absence interpretation, and
   MUST NOT treat "absent from a variant-only callset" as hom-ref. Documentation, no schema.
2. **Reserve `requires_callable`** as a row-level boolean (on the open `flags` list initially, or a
   reserved boolean column) marking rows where the *absence* of a variant is the informative call —
   recessive carrier screening, "pathogenic variant absent" reassurance. A consumer lacking
   callability data then knows to withhold the reassuring conclusion (degrade to unknown) rather
   than assert it.

**Open question:** `requires_callable` as a reserved **flag** (fits the existing open `flags` list,
zero schema change) or a reserved **typed boolean column** (queryable, but a new column)? We lean
flag for 0.4, promotable to a column later if consumers need to filter on it.

---

## B1 — PGx star-alleles (endorsed, three refinements)

The 0.4 four-table model (junction `haplotypes.csv`; `allele_function.csv`; per-gene
`activity_phenotype.csv`; `diplotypes.csv` fallback; CN as an attribute of the *cis* allele-unit) is
confirmed by the consumer's three-caller stack (Aldy / Cyrius / PharmCAT) and stands. Three
additive refinements land:

1. **First-class unresolved** — via the shared binning `unresolved` outcome above. On 30× short-read
   Cyrius returns `Genotype=None`; the phenotype is `unresolved`, never "Normal Metabolizer".
2. **Caller provenance** — via the reserved T2 triple.
3. **Optional suballele column** on `allele_function.csv` (Aldy's `Minor` `1.001;1.012`), with the
   **core star-string as the required key**. Suballele is optional-extra, not identity.

**Open question:** for tandems/hybrids (`*36+*10`, `*68+*4`) — confirm the star-string-verbatim-as-
identity approach (SVs live in the name, `sv_type`/`copy_number`/`hybrid_orientation` are optional
parsed conveniences) matches how Aldy/Cyrius hand you these, so we don't over-structure the SV field.

---

## B2 — `repeat_alleles.csv` (VNTR/STR)

Accepted as a binning table keyed on **`(gene, repeat_unit)`** — the motif is part of the identity
(T3). Two callers gave DAT1 `21/41` vs `3/3` on the *same* sample because they counted different
motif definitions; a bare `repeat_count` with no motif is non-comparable. The count is a **consumer**
call (ExpansionHunter / adVNTR / a span genotyper), never authored, and the consumer's call MUST
state the motif it counted. Frozen shape:

```csv
gene, repeat_unit, measure_kind, measure_min, measure_max, direction, clin_sig, phenotype, trait_efo_id, conclusion, unresolved
HTT, CAG, repeat_count, 40, , risk, pathogenic, "Huntington disease (full penetrance)", MONDO_0007739, "≥40 CAG — fully penetrant", false
HTT, CAG, repeat_count, 36, 39, risk, pathogenic, "Huntington disease (reduced penetrance)", MONDO_0007739, "36–39 CAG — reduced penetrance", false
HTT, CAG, repeat_count, 27, 35, neutral, uncertain_significance, "Intermediate allele", MONDO_0007739, "27–35 CAG — intermediate", false
```

The complex-VNTR **motif-path** form (DAT1 `A-A-B-C-D-…`) is noted as the natural home for the
Constitution's sanctioned declarative-grammar escape hatch (a regex over an allele string) *if* a
plain count proves too coarse — **not** a near-term ask.

**Open question:** for loci where the motif itself is ambiguous across references (5-HTTLPR
short/long vs base counts), is `repeat_unit` a free-form motif string, or do you want it constrained
to an IUPAC/ACGT pattern so the format can validate it?

---

## B3 — `heteroplasmy.csv` (mtDNA)

Accepted as an `allele_fraction` (0–1) binning table, keyed on `(gene, reference_sequence)` per A3.
Maps directly to the consumer's `heteroplasmy_AF`. Homoplasmic calls remain reachable via the 0.3
item-5b single-allele genotype; the haplogroup fits the item-7 haplotype table with a single allele
slot, `Quality`/`Rank` being a caller-confidence axis (T2). The `NOT_CALLED` rejected-artifact row
maps to the `unresolved` outcome.

**Open question:** heteroplasmy penetrance thresholds are locus- and tissue-dependent (blood vs
affected tissue). Should the format carry a `tissue`/`assay_context` note on these rows, or is that
firmly consumer-side? We lean consumer-side, but flag it because it changes the phenotype meaning.

---

## B4 — CNV dosage with an optional modifier (SMN)

Accepted with the **column** approach, not the tuple key. SMA phenotype is a function of `SMN1_CN`
*and* `SMN2_CN` (SMN2 is a well-established dosage modifier) — so the row genuinely needs a compound
key. But a compound key in a relational/CSV contract is spelled with **explicit named columns
(multicolumn keying), never a packed `(gene, cn)` tuple.** A tuple-as-key is an ad-hoc coder shortcut,
not a protocol idiom: it is opaque to a plain CSV reader, unqueryable per-component, and order-fragile.
Multicolumn keying already exists and says the same thing legibly, so we use it. (Design-stance, not a
Constitution invariant — but a firm one: keys in these tables are always named columns.) Concretely,
`copynumbers.csv` keeps its scalar `gene` key and gains an **optional, nullable `modifier_gene` +
`modifier_cn` pair**:

```csv
gene, copy_number, modifier_gene, modifier_cn, measure_kind, direction, clin_sig, phenotype, trait_efo_id, conclusion, unresolved
SMN1, 0, SMN2, 3, copy_number, risk, pathogenic, "SMA (milder, 3 SMN2 copies)", MONDO_0011226, "0 SMN1 / 3 SMN2", false
SMN1, 0, SMN2, 1, copy_number, risk, pathogenic, "SMA (severe, 1 SMN2 copy)", MONDO_0011226, "0 SMN1 / 1 SMN2", false
SMN1, 1, , , copy_number, risk, carrier, "SMA carrier", MONDO_0011226, "1 SMN1 copy — carrier", false
```

Single-gene dosage rows leave the modifier columns null. Plus the recurring pair: caller provenance
(T2, `SMNCopyNumberCaller v1.1.2`) and the unresolved outcome (T1 — a segmental-duplication region
at ~20× is often *not resolved*, `METHOD_BLIND_SPOT`, never "2 copies").

**Open question:** is a **single** modifier pair enough for every dosage locus you run, or are there
loci needing two or more modifiers? If one covers all real cases, we freeze exactly one pair. If a
locus ever needs two-plus modifiers, the answer is a second named pair (or a small `dosage_modifiers`
side table), **not** a tuple key — the keying stance above holds regardless.

---

## B5 — `pgs.csv` freeze (item 8) — going beyond the standing roadmap

The roadmap kept item 8 note-only because just-prs has no combine-into-one-score primitive, so
per-PGS weights would be dead data. That reasoning holds for *weights* — but the anti-misuse fields
the consumer names are a one-way door independent of the combine question, and the highest-stakes
module type. **We freeze the full shape this run:**

```csv
pgs_id, trait_efo_id, note, group, training_ancestry, match_rate, research_tier
```

- **`training_ancestry`** — population(s) the score was derived/validated in, so a consumer can
  refuse or caveat an out-of-ancestry application instead of silently miscalibrating. This is the
  ancestry parameter axis the binning primitive (B0) leaves room for.
- **`match_rate`** — carries the consumer's hard floor (`> ~20%` variant mismatch invalidates the
  score); a consumer needs the floor to reject a score computed on too few matched variants.
- **`research_tier`** — pins as *data* the rule that a PRS yields a Z/percentile within a matched
  reference distribution, **never an ancestry-calibrated absolute risk**, and `|Z| ≥ 2.5` in a
  healthy proband is a population-stratification signal, not a disease prediction. This keeps a
  downstream UI from rendering a EUR-frame percentile as personal risk for a non-EUR sample.
- Plus the existing `note` / `group` and an optional header `quality_floor`, mirroring just-prs's
  `demo-trait-filter.json`.

**Open questions (these gate the freeze):**

- **`training_ancestry` vocabulary** — 1000G superpopulation codes (`EUR/EAS/AFR/AMR/SAS`), a free
  string, or a list (multi-ancestry scores)? We lean a `list[str]` of superpopulation codes as an
  open `frozenset`.
- **`match_rate`** — do you want the *floor* stored per-row (author sets the threshold) or the
  *observed* match rate stored by the consumer at scoring time, or both (author floor + consumer
  observed)? These are different fields; naming both now avoids a later split.
- **`research_tier`** — a boolean (`is_research_only`) or an open vocabulary
  (`{research_only, calibrated, …}`) so a future ancestry-calibrated score can declare itself?

---

## B6 — `actionability` axis (reserved, note-only)

Accepted as a **reserved-namespace note**, respecting the non-goal boundary the consumer drew:
annotation-level **actionability** of the finding (treatable / preventable / pharmacogenomic /
incurable / reproductive; on the ACMG secondary-findings list or not) is a property of the
gene–condition–intervention triad = *data*; the consumer's **disclosure policy** (whether/how to
return a result to a person) stays consumer-side. We reserve the name `actionability` as an open
vocabulary a module *may* carry and a consumer's return-of-results policy *may* read, without the
format itself deciding disclosure.

**Open question:** confirm the seed vocabulary `{actionable, preventable, pharmacogenomic, incurable,
reproductive}` and whether ACMG-SF membership is a *value* in this axis or a separate reserved flag
(`acmg_sf`). We lean separate flag — ACMG-SF is a list-membership fact, actionability is a category.

---

## What we do NOT take this run

- **One physical binning table** (B0 literal form) — superseded by shared-vocabulary/per-quantity
  tables above.
- **Tuple binning keys** (B4 literal form) — superseded by the optional modifier column.
- **The complex-VNTR motif-path grammar** (B2) — reserved as the escape-hatch home, not built.
- **Authored PRS weights** (`effect_allele`+`effect_weight` scoring file) — remains the separable,
  heavier follow-up; `pgs.csv` is a manifest of PGS Catalog IDs, not authored weights.

---

## Round-2 checklist for the consumer

The freeze waits on these answers (all flagged inline above):

1. Binning range convention — half-open `[min,max)` vs inclusive; `unresolved` sentinel-row vs enum.
2. Provenance triple — three columns vs one composite string.
3. `reference_sequence` — validated accession vocabulary vs free-form + warning.
4. `requires_callable` — reserved flag vs typed boolean column.
5. Repeat `repeat_unit` — free-form motif vs constrained ACGT/IUPAC pattern; 5-HTTLPR handling.
6. Heteroplasmy — is `tissue`/`assay_context` in-format or consumer-side?
7. CNV modifier — is one `modifier_gene`/`modifier_cn` pair enough for every dosage locus?
8. `pgs.csv` — `training_ancestry` vocabulary; `match_rate` author-floor vs consumer-observed vs both;
   `research_tier` boolean vs vocabulary.
9. `actionability` — seed vocabulary; ACMG-SF as value vs separate `acmg_sf` flag.
