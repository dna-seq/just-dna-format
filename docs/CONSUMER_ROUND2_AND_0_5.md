# Consumer round-2 response + 0.5 idea-book

*Answers to [`PROPOSAL_0_4.md`](PROPOSAL_0_4.md)'s round-2 checklist from production data, a review of
the sample implementation (`vocab`/`binning`/`pgx`/`pgs`), and — in the spirit of the two-way
collaboration — a book of **0.5 ideas grounded in our WGS pipeline**, kept inside the one constraint
the consumer named: it stays **VCF-based, possibly augmented on top.***

**Status: consumer round-2 — design input, not a shipped contract.** Written after re-reading the
Constitution and the new `CLAUDE.md` data-agnostic north star. The round-2 answers are meant to let
you **freeze the bytes**; the 0.5 ideas are deliberately looser (you asked for imagination).

> ---
> ### ↳ maintainer disposition — round-2 actioned in the sample (`vocab`/`binning`/`pgs`)
>
> This copy is **annotated inline**, mailing-list style. All nine answers are actioned or confirmed;
> both review catches worth code (C1, C3) are built; C2 is a doc decision. Concretely landed on the
> branch (schema-only — compiler still deferred, `artifact.digest` still unchanged):
> - **C1** → a table-level `validate_bins(rows)`: rejects overlapping resolved ranges within
>   `(key…, trait_efo_id)`, warns on interior coverage gaps; the "measured-but-no-bin" third state is
>   documented distinct from `unresolved`.
> - **3a `source_field`** → **pulled into 0.4** as an optional VCF field-binding on `MeasureBinRow`,
>   constrained to a bare field-name token (optionally `|`-alternated) so it stays a **declarative
>   pointer, not an expression** (Principle 1 — indirection, not computation).
> - **Q3** → `HeteroplasmyRow.reference_sequence` rejects the legacy `NC_001807` landmine.
> - **Q6** → optional `tissue`/`assay_context` built on `HeteroplasmyRow` (+ it joins the heteroplasmy
>   key), so bins are explicitly tissue-conditional — accepting your divergence from our consumer-side lean.
> - **Q8** → `match_rate` renamed **`match_rate_floor`** (floor only; observed = measurement =
>   consumer-side, per the north star); optional **`training_cohort`** added; `research_tier` stays a vocab.
> - **Q9** → `actionability` seed extended with `descriptive`/`modifiable`; **`acmg_sf`** reserved as a
>   separate flag. **Q2/Q4** → `caller`/`caller_version`/`reference_db` stay three reserved names;
>   `requires_callable` stays a reserved flag (column expected later); `callable_from` newly reserved (0.5).
> - **0.5 idea-book** → `source_field` (3a) taken now; the verification-harness (3b) has **no blocker
>   and no format deliverable** — it's buildable on 0.4 today as a `just-dna-lite` consumer, and its
>   report-card output is per-sample results (consumer-side per the north star). See the reply at the end.
> ---

---

## Part 0 — the new edition reads well

The round-1 asks landed faithfully, and the **two places you diverged from my literal proposal are
better than what I asked for** — I want to endorse both explicitly so they freeze with confidence:

- **B0 — shared column *vocabulary*, per-quantity tables (not one physical `measure_bins.csv`).**
  Correct. One physical table would have forced PRS's ancestry axis and the per-quantity keys into a
  contorted shape; the shared `measure_kind/measure_min/measure_max/…/unresolved` vocabulary gets the
  single "bin-a-measure" consumer code path — the actual win — without that cost. The `unresolved`
  sentinel-row-with-null-bounds is exactly right, and making it **mandatory** on the primitive (not
  per-table discretion) is the single most important safety decision in the whole 0.4 — it is the
  generalization of the two collapses my pipeline audit turned up (a Cyrius `None` rendered as
  "Normal Metabolizer"; a no-call rendered as a negative). Baking it into the type is stronger than
  any rule.
- **B4 — optional `modifier_gene`/`modifier_cn` columns, not a tuple key.** Correct, and the reasoning
  ("a tuple-as-key is a coder reflex, opaque to a CSV reader, unqueryable per-component") is exactly
  the right instinct — it's the same "orthogonal, legible columns" discipline as Principle 5, applied
  to keys. Multicolumn keying says the same thing legibly.
- **The `CLAUDE.md` data-agnostic north star** ("a module holds no measurement; the measurement is
  supplied by the consumer at query time; the schemas generalize a practical subset, not a totality")
  is the right frame, and it **retroactively sharpens B0**: the `copy_number`-as-a-measured-value slip
  (which I made too, in the field notes) is precisely a north-star violation — the module holds the
  *range*, never the *count*. Dropping the `copy_number` column in favor of `measure_min==measure_max`
  is the correct consequence. I'd only add: this north star is also what cleanly answers your `pgs.csv`
  `match_rate` question below (the *observed* match rate is a measurement → consumer-side; only the
  *floor* is annotation → in-module).

I read `vocab`/`binning`/`pgx`/`pgs` line by line and **found no bugs** — the validators are tight
(the `unresolved` XOR-bounds rule, the modifier-pair XOR, the `[0,1]` heteroplasmy bounds, the
`extra="forbid"` reserved-namespace boundary). The catches below are **design** points, not defects.

---

## Part 1 — review catches from the sample implementation

### C1 (the one worth acting on) — "measured but no bin" ≠ `unresolved`; bins need an exhaustiveness/overlap contract

`unresolved` (T1) handles *no measurement*. It does **not** handle a **measurement that is present but
matches no bin** (a gap) or **matches two bins** (an overlap). These are a distinct third state, and
today the schema is silent on it:

- **Gap:** `repeat_alleles.csv` for HTT defines 27–35 / 36–39 / ≥40. A real `REPCN=15` matches *no
  row*. Is that "normal" (safe, but only if a `≤26 normal` row exists), "no result," or an error? In
  our pipeline the HTT counter **always authors the reference bin explicitly** (`≤26 → normal`) so
  every possible count hits exactly one bin — the absence of a normal bin is how a real report
  silently drops a normal call.
- **Overlap:** two resolved rows whose ranges intersect select two phenotypes for one measurement.
  This is **legitimate across traits** (a repeat count binning to two `trait_efo_id`s — the same
  pleiotropy `DiplotypeRow` already allows via multiple rows) but **ambiguous within one trait**.

**Suggestion (cheap, high-value):** a table-level validator `validate_bins(rows)` that, grouped by
`(key…, trait_efo_id)`, rejects overlapping resolved ranges and (optionally, as a *warning*) flags a
gap in coverage. Plus a one-line consumer-contract note: *a measurement present but matching no bin is
"no matching bin," which is distinct from `unresolved`; author the reference bin to avoid it.* This is
the row-level `unresolved` safety property lifted to the table level — and it's where our "always
author the normal bin" discipline would have saved us a class of silent-normal bugs.

> **↳ maintainer reply — C1: built.** `binning.validate_bins(rows)` groups by `(_KEY_FIELDS…,
> trait_efo_id)` and **raises** on overlapping resolved ranges (inclusive), so one measurement never
> selects two phenotypes within a trait; overlap *across* traits is allowed (pleiotropy). It returns
> **warnings** for interior coverage gaps — for integer kinds a hole spanning ≥1 uncovered integer
> (your missing-36-39 case), for continuous fractions any positive hole; `activity_score` is
> consumer-summed/quantized so its interior "gaps" aren't flagged (avoids false positives on a correct
> CYP2D6 table). One honest limitation: the **missing edge/reference bin** (no `≤26 normal`) is *not*
> auto-detected — without a known domain floor it would false-positive — so it stays a documented
> consumer-contract note ("author the reference bin"), plus the "measured-but-no-bin ≠ `unresolved`"
> distinction is now in the docstring. The modifier is part of `CopyNumberRow._KEY_FIELDS`, so two
> sharp `SMN1=0` rows differing only by SMN2 CN are distinct keys, not a spurious overlap.

### C2 — `float` bounds are *correct* (half-repeats are real), but STR microvariant notation needs a decision

Endorsing `measure_min/max: Optional[float]` (not `int`) for `repeat_count` — this looks like it
should be integer, but **our VNTR work proves fractional repeats are real**: MAOA-uVNTR **3.5R**, the
"5R"-that-is-really-4.5R half-repeat, DRD4 partial units. So `float` is right and load-bearing.
**But** one subtlety your callers will hit: forensic/STR **microvariant notation** like TH01 **"9.3"**
does *not* mean the decimal 9.3 — it means "9 full `TCAT` repeats **+ 3 extra bases**" (a partial
repeat). A binning bound of `9.3` as a float would sort between 9 and 10 (accidentally OK for
ordering) but *means* something the float doesn't capture. **Open question back to you:** for STR loci
with microvariants, is a plain float bound enough (treat 9.3 as "between 9 and 10, closer to 10"), or
does `repeat_count` binning need a note that the value is a `full.partial` convention, not a decimal?
For pathogenic-threshold loci (HTT CAG) it never matters; for forensic-style STRs it can.

> **↳ maintainer reply — C2: `float` kept; microvariant handled by a doc note, not a type change.**
> Agreed `float` is load-bearing (half-repeats). For the `9.3` microvariant case we'll **not** overload
> the float with `full.partial` semantics (that would be a second meaning smuggled into one number —
> the same anti-pattern as the old `state`). A bin bound stays a plain magnitude for ordering; the
> reference docs note that for forensic STRs the `full.partial` allele *name* is a distinct string
> (a candidate for the reserved repeat motif-path / allele-string escape hatch), not the binning
> bound. Pathogenic-threshold loci are unaffected. If a real forensic module needs the exact
> convention, that's a round-3 item — flag it and we widen additively.

### C3 — document the diplotype canonicalization rule in the *CSV contract*, not only the code

`DiplotypeRow._canonicalize_pair` sorts **lexicographically** (`*10 < *2`, because `'1' < '2'`). That
is fine for order-independence *provided the consumer canonicalizes identically*. A consumer that sorts
star-alleles **numerically** (`*2` before `*10`) would miss the row. The code comment says it; the
**CSV-facing contract** must too — one line: *"the pair is stored lexicographically-sorted on the
star-string; a consumer must sort identically before lookup."* (Minor, but it's a silent-miss if
undocumented.)

> **↳ maintainer reply — C3: documented.** Good catch — `*10 < *2` lexicographically is a real
> silent-miss. The CSV contract line ("`diplotypes.csv` stores the pair lexicographically-sorted on
> the star-string; a consumer MUST sort identically before lookup") is now in `REFERENCE_EXAMPLES.md`
> beside the APOE table, not only in the code comment.

*(Non-catches, for the record: `HaplotypeRow.gene` optional + `DiplotypeRow.gene` required is the
right split; `activity_value` unbounded is correct — duplications give `*1x2 = 2.0`; the
`STAR_ALLELE_PATTERN` correctly rejects malformed strings like `*(1` that we've actually seen leak
from a caller.)*

---

## Part 2 — round-2 checklist, answered from production data

Crisp calls so you can freeze. Each is grounded in a concrete artifact.

**Q2 · Provenance triple — one composite string vs three columns → THREE COLUMNS.** Our callers pin
the three separately and we filter on them independently: Aldy's header is
`gene=CYP2D6-pharmvar-6.2.14; cpic=…; cpic_score=…`; Cyrius/SMNCopyNumberCaller pin their tool version
in their own field; the reference DB (`pharmvar-6.2.14`) is a separate axis we query ("all calls made
against pharmvar 6.2.14"). A composite `aldy@6.2.14/pharmvar-6.2.14` would just force everyone to
re-split. Reserve `caller` / `caller_version` / `reference_db` as three.

**Q3 · `reference_sequence` — validated accession vocab vs free-form+warning → SMALL VALIDATED SET +
HARD-WARN ON LEGACY.** The hazard is *specific and enumerable*, which is the ideal case for a closed
guard: `NC_012920.1` (rCRS) is safe; **`NC_001807` (legacy) produced a confidently-wrong `H2a2a1`
haplogroup in our chip-mtDNA pipeline** because coordinates and reference bases silently disagree and
`genome_build=GRCh38` doesn't disambiguate. So: accept a small validated set of canonical MT
accessions, and **error-or-loud-warn on the known-dangerous legacy accessions** (a reserved
danger-list). Free-form invites typos; a fully-closed set is too rigid for future refs — the
warn-on-legacy middle is what our scar tissue argues for.

**Q4 · `requires_callable` — reserved flag vs typed boolean → FLAG for 0.4 is fine to start, but plan
for a column.** Your lean is right for shipping. Heads-up from our side: callability is not a niche
axis for us — it's a *heavily-filtered* first-class state (our oracle enum
`CONFIRMED_NEGATIVE`/`LOW_DP_NEG`/`UNCOVERED`, and a hard rule that "a named negative is assertable
*only* where proof_status=CONFIRMED_NEGATIVE"). So consumers *will* want to `WHERE requires_callable`
— promotion to a typed boolean column will come. Ship the flag; expect the column.

**Q5 · `repeat_unit` free-form vs ACGT/IUPAC; 5-HTTLPR → FREE-FORM (allow long motifs); and 5-HTTLPR
is NOT a `repeat_count` locus.** Two things:
- Constrain to short ACGT and you break our real VNTRs: **DRD4 exon-3 (~48 bp composite unit), DAT1
  (~40 bp unit)** are large composite motifs, not `CAG`-style trinucleotides. Keep `repeat_unit`
  free-form (optionally *warn* if it's not `[ACGTN]+`, never *reject*).
- **5-HTTLPR does not fit `repeat_alleles.csv` at all.** It is a biallelic **structural indel** (a
  ~43 bp insertion → **Short / Long** alleles), not a repeat *count*; forcing it into `repeat_count`
  is a category error. It belongs in the **genotype/haplotype** model (an `S`/`L` two-state call,
  which your 0.3 item-5b widened genotype or a 2-allele `HaplotypeRow` already expresses — and note it
  is usually read *phased with `rs25531`*, so it's a mini-diplotype). Worth a one-line note in the
  reference examples so authors don't reach for the repeat table.

**Q6 · Heteroplasmy `tissue`/`assay_context` — in-format vs consumer-side → RESERVE IT IN-FORMAT (at
least as a documented caveat + reserved name), diverging from your consumer-side lean.** Reason: tissue
doesn't just annotate the row, it **changes the phenotype the bin means.** A blood-derived heteroplasmy
fraction systematically *under-represents* the affected-tissue burden (MELAS `m.3243A>G` at 11% in
blood is a different clinical object than 11% in muscle), and the penetrance *threshold itself* is
tissue-dependent — so the same `allele_fraction` bins to different phenotypes by tissue. Our data is
all blood-WGS, which is exactly the under-calling case. You don't have to make `tissue` a key, but a
heteroplasmy binning table with no tissue context is quietly unsafe; reserve `tissue`/`assay_context`
and document that the bins are tissue-conditional.

**Q7 · CNV modifier — is one `modifier_gene`/`modifier_cn` pair enough → YES, one pair covers our real
loci.** SMN1/SMN2 is the canonical modifier case. The other paralog-dosage loci we run (CYP21A2 /
CYP21A1P, HBA1 / HBA2) are reported as *total functional copy number*, not a modifier chain. Freeze one
pair; if a locus ever needs two-plus, your fallback (a small `dosage_modifiers` side table) is right —
not a tuple key.

**Q8 · `pgs.csv` — three sub-answers:**
- **`training_ancestry` vocabulary → superpop `list[str]` `{EUR,EAS,AFR,AMR,SAS,multi}` is the right
  *required floor*, but it is too coarse for the real transferability caveat — add an optional
  free-form finer note.** Superpop granularity catches the biggest miscalibrations (our South-Asian
  sample on a EUR-trained score → SAS≠EUR, caught at superpop level). But our cross-population
  calibration shows the mismatch is often *within* a superpop (a Northwest-EUR-trained score applied to
  a South-EUR/Ashkenazi/Finnish sample), which superpop codes cannot express. Keep the closed superpop
  `frozenset` as the required field; add an **optional** `training_cohort` free-string for
  sub-superpop precision when the author knows it.
- **`match_rate` — floor vs observed vs both → the FLOOR belongs in the module; the OBSERVED does
  NOT** (your own data-agnostic north star decides this cleanly). The author-set floor (`> ~20%
  mismatch invalidates`) is *annotation policy* → lives in `pgs.csv`; suggest renaming it
  **`match_rate_floor`** for clarity. The *observed* per-sample match rate is a **measurement** → by
  the north star it is consumer/runtime, and must **not** live in the module. So: one field
  (`match_rate_floor`), not two — the second would violate the principle you just wrote down.
- **`research_tier` — boolean vs vocabulary → VOCABULARY `{research_only, calibrated}` (your choice is
  right).** Future-proofs a genuinely ancestry-calibrated score declaring itself. Every PRS we ship
  today is `research_only` (Z/percentile within a matched reference, never an absolute risk), so the
  vocab starts one-valued in practice but the second value is the one-way-door insurance.

**Q9 · `actionability` seed vocab + ACMG-SF → extend the seed with `descriptive`/`modifiable`;
ACMG-SF as a SEPARATE `acmg_sf` flag.** Your seed `{actionable, preventable, pharmacogenomic,
incurable, reproductive}` maps cleanly onto our disclosure routing
(`actionable-informed`/`incurable-gated`/`reproductive-routed`/`pgx-conditional`). Two additions our
corpus needs: **`descriptive`** (a *large* fraction of our findings are self-knowledge /
COMMON-NOT-CAUSAL / no-action — they must have an actionability value that says "none," not be forced
into `actionable`) and **`modifiable`** (lifestyle-actionable, distinct from clinical `actionable`).
ACMG-SF membership is a **list-fact** (the 84-gene list), orthogonal to the category — a gene is *on
the list* or not, independent of whether it's `actionable`/`incurable` — so a separate reserved
`acmg_sf` boolean is right, not a value in the axis. (This keeps the same orthogonality discipline as
Principle 5.)

**B1 open Q · star-string-verbatim for tandems/hybrids matches Aldy/Cyrius? → YES, exactly — don't
over-structure the SV field.** Cyrius hands us the string as truth (`Raw_star_allele`) *plus* a
*decomposed* structural picture in separate fields (`Total_CN`, `Spacer_CN`, `Exon9_CN`,
`CNV_consensus`) — which is precisely your "string is identity; `sv_type`/`copy_number`/
`hybrid_orientation` are optional parsed conveniences" design. One refinement: Cyrius's decomposition is
*finer* than a single `copy_number` (it splits spacer vs exon9 CN), so leave the optional parsed fields
genuinely optional and open — a consumer may fill `copy_number` or may carry a richer structural note;
the star-string remains the join key either way.

---

## Part 3 — a 0.5 idea-book (grounded in our pipeline, VCF-based, with some imagination)

Framing: everything below **stays VCF-based** (the sample side is always a VCF, possibly augmented),
and stays inside the Constitution (modules are declarative data; a runner is a consumer; integrity
makes results reproducible). None of it is a round-2 ask — it's the "throw ideas over the fence" half
of the collaboration.

### 3a — the missing bridge: let a module *declare where its measurement lives in a VCF*

Today the contract is "the consumer supplies the measurement." The cheapest, highest-leverage 0.5
move is to let a module **optionally declare the VCF field its measurement is extracted from**, so the
extraction becomes deterministic instead of consumer-improvised:

```
# a binning table row (or a table header) gains an optional field-binding:
source_field = REPCN     # repeat_count  ← ExpansionHunter FORMAT/REPCN
source_field = AF        # allele_fraction ← Mutect2-mito FORMAT/AF (heteroplasmy)
source_field = CN | DS   # copy_number   ← <CNV> FORMAT/CN, or imputed dosage DS
callable_from = DP,GQ,FT # the three-state callability signal (see 3d)
```

This is the natural home for VNTR: an **ExpansionHunter VCF already carries everything**
`repeat_alleles.csv` needs — `INFO/RU` (repeat unit → your `repeat_unit` key), `FORMAT/REPCN` (the
`repeat_count` measurement, e.g. `17/42`), `REPCI` (CI), and the read-evidence fields
`ADSP`/`ADFL`/`ADIR` (spanning / flanking / in-repeat → a callability/confidence signal). A module that
declares `repeat_unit=CAG, source_field=REPCN` is consumable from a real EH VCF **with zero glue**. The
symbolic-allele conventions VCF already has (`<STR n>`, `<CNV>`, `<DUP>`, `<DEL>`, `<CN0>`) are the
"augmented on top" surface — the format doesn't invent a representation, it *binds to* the VCF one.

### 3b — modules as a **deterministic verification harness** (your stated use case, developed)

You framed the real prize: the module machinery as a **reproducible, template-driven checker** — SNP
panels, PRS panels, personal before/after modules, "how does my panel look on each caller, with/without
liftover" — so an agent **stops hand-writing greps** (every hand-grep is an error/hallucination
surface). This is a genuinely new *purpose* for the format, and it fits its principles unusually well:

1. **A panel is already a module** (a set of loci + expected genotypes/bins). Add a small
   **evaluation-output contract** — a "report card" schema the runner emits per locus:
   `{locus, module_expected, vcf_observed, callability, bin_selected, verdict∈{match,mismatch,no-call,unbinned}}`.
   Data-in (module + VCF), data-out (a validated table). No agent prose in the loop.
2. **Cross-condition diff — the killer case.** Run the *same* content-addressed module against **N
   VCFs** (Clair3 vs GATK vs DeepVariant; `±liftover`; pre- vs post- a pipeline change) and emit a
   **concordance/diff table**: per locus, the genotype under each condition + a concordance verdict.
   Because the module's identity *is* its digest and the runner is deterministic, "did my panel change
   after I touched the pipeline?" becomes a **byte-level diff of two report cards**, not a manual
   re-read. That is exactly the regression check you described (per-caller, ±Liftover), and it is the
   single biggest agent-error-reduction lever I can see: the assertion set is *frozen data*, so the
   agent can't hallucinate the expectation.
3. **Personal modules.** A user's own curated locus set as a content-addressed module → re-checked
   deterministically on every pipeline change; integrity=identity means the check is auditable and
   diff-able across time.
4. **Why the Constitution *helps* here:** declarative-not-code is what makes a shared/downloaded panel
   *safe to run as an assertion* (no code executes); integrity-as-identity is what makes the
   before/after diff *trustworthy*; the mandatory `unresolved`/callability contract is what stops a
   "no-call under caller B" from masquerading as a "mismatch vs caller A." The verification-harness is
   almost a free rider on properties you already froze.

This might be a **new consumer** (a "module evaluator" living in `just-dna-lite`) more than a format
change — the format's contribution is just the **evaluation-output schema** + the **field-binding**
declaration (3a). But it turns the catalog into a QC instrument, which is where it earns its keep in a
real pipeline.

### 3c — augmented-VCF as the landing pad for our cracked short-read loci

We have short-read callers for loci a standard VCF doesn't represent (PER3 flag-to-flag span, DAT1
motif-path, 5-HTTLPR junction-k-mer + `rs25531` phasing, MAOA-uVNTR half-repeat). Right now their
output is bespoke TSVs. The clean 0.5 story: **emit them as an *augmented* VCF** — a synthetic `<STR>`
record carrying `INFO/RU` (our motif), `FORMAT/REPCN` (our genotype, incl. half-repeats like `3.5`),
and our evidence counts in custom `FORMAT` fields (spanning / flanking / independent-molecule support).
Then a `repeat_alleles.csv` module consumes them **through the same `source_field=REPCN` path as
ExpansionHunter** — our hard-won niche genotypes become format-native with no special case. This closes
the loop between "the format only defines the table" and "our callers produce the measurement": the
augmented VCF is the interface.

### 3d — smaller VCF-native ideas

- **Callability as a FORMAT-derived three-state.** Our single most expensive lesson (no-call ≠
  hom-ref) is computable from a VCF: `DP/GQ` (and `FT`, or a gVCF ref-block) → `covered-hom-ref` vs
  `no-call`. A 0.5 runner that derives the three-state per locus (and feeds it into `requires_callable`
  rows) would give every consumer the safety property for free, from standard fields.
- **Phasing-aware panels.** VCF `PS`/`HP` already carry phase; a module that declares it needs phased
  input (the `phased` flag exists) lets the runner do cis/trans correctly for compound-het panels and
  for star-allele phasing (`*2×2/*4` vs `*2/*4×2`) — the exact case your `pgx.py` docstring calls out.
- **Multi-sample / trio panels.** VCF is natively multi-sample; a panel module could carry a
  Mendelian-consistency or de-novo assertion (our trio validation is exactly this), emitted as another
  report-card verdict. Purely a consumer feature, but the module (the panel + the expected inheritance)
  is declarative data.

---

## Closing

The ping-pong is working: you actioned A2, accepted the asks, improved two of them, and handed back a
sharp round-2 — and this round answers all nine open questions from real caller data so you can freeze.
The 0.5 idea-book is the reciprocal half: the field-binding (3a) + verification-harness (3b) is, for
*us*, the feature that would turn the format from "annotation catalog" into "the thing the agent runs
instead of hand-grepping" — which is where it stops being a nice-to-have and starts removing a whole
class of our errors. Take what's useful, reject what isn't; that's the deal.

> ---
> ### ↳ maintainer reply — the 0.5 idea-book
>
> - **3a field-binding — taken now, not deferred.** `source_field` landed in 0.4 (optional, on every
>   binning table), because it's cheap, additive, and — your sharpest framing — it's *indirection, not
>   computation*. We enforced that structurally: `source_field` must be a bare VCF field-name token
>   (optionally `|`-alternated, `CN|DS`), never an expression, so it stays a **declarative pointer**
>   inside Principle 1. An EH VCF (`INFO/RU` → `repeat_unit`, `FORMAT/REPCN` → the measure) is now
>   consumable with zero glue via `repeat_unit=CAG, source_field=REPCN`. `callable_from` is reserved
>   for the 3d callability signal (0.5).
> - **3b verification-harness — strongest idea, but there is *no blocker and no 0.4 deliverable*.** We
>   pushed on "what does the format need to add for this?" and the honest answer is **nothing**: the
>   harness is a pure consumer, buildable on 0.4 (even 0.3) today. A panel is already a module (loci +
>   expected genotypes/bins — no new type); extraction is the consumer's job and `source_field` now
>   tells it which VCF field to read; `artifact.digest` already makes a before/after report-card diff
>   byte-level and trustworthy; the mandatory `unresolved`/callability contract already stops a
>   "no-call under caller B" masquerading as a "mismatch vs A". The one thing that *looked* like a
>   format artifact — a standardized **evaluation-output schema** (`{locus, observed, callability,
>   bin_selected, verdict}`) — is **per-sample results, i.e. a measurement**, so by the data-agnostic
>   north star it stays consumer-side (a `just-dna-lite` contract), **not** in `just-dna-format`. So 3b
>   is a `just-dna-lite` feature whose only format dependency (field-binding) already shipped. The
>   format "helps" purely by the properties it already froze — declarative-not-code makes a downloaded
>   panel safe to run, integrity makes the diff trustworthy. Nothing to schedule here.
> - **3c augmented-VCF — endorsed as the interface** for your cracked short-read loci (a synthetic
>   `<STR>` record with `INFO/RU` + `FORMAT/REPCN` + custom evidence fields), consumed through the same
>   `source_field=REPCN` path. No special case — exactly the "the format binds to the VCF, doesn't
>   reinvent it" line. **3d** (callability three-state, phasing-aware, trio) is consumer-side; the only
>   reservations are `callable_from` (done) and the existing `phased` flag.
> - **Charter check:** none of this adds code-in-cells or network; the module stays declarative data,
>   the runner is a consumer, integrity makes the check reproducible. The verification-harness is a
>   free rider on properties already frozen — which is why it fits.
> ---
