# Reference examples — worked module drafts

These are **hand-authored sketches** of how modules are expressed with the 0.3/0.4 features (see
[ROADMAP.md](ROADMAP.md), [PROPOSAL_0_4.md](PROPOSAL_0_4.md)). They are **ideas and drafts for module
authors and consumers** — a picture of the intended shapes. Column sets, vocab, and file names may
still change during the 0.4 round-2 vetting. rsIDs / coordinates / effect sizes are illustrative.

This doc is the **"conclusion" stage of the feedback → schema cycle** (see
[`USE_CASES.md`](USE_CASES.md) → *The feedback → schema cycle*): where a use case, once its blockers
are resolved into a settled shape, becomes *how to do it now, with these bricks*. For the
*is-it-reachable-and-what's-missing* analysis of the same use cases, read `USE_CASES.md` first.

**The 0.4 relational/quantitative tables in §2, §4–§8 are now schema-validated** by the sample
implementation in `just_dna_format.{binning,pgx,pgs}` (see `schema/tests/test_v04.py`). Every CSV row
below round-trips through its Pydantic model. The compiler does **not** yet materialize them into
parquet — that is deferred until the shapes freeze (PROPOSAL_0_4).

**Conventions the sample settled:**
- **Modules compose from optional table kinds (one CSV = one concern).** The only always-present file
  is `module_spec.yaml`; every table below is optional. A SNP module is just `variants.csv`
  (+ `studies.csv`); a PGx module adds `haplotypes`/`allele_function`/`diplotypes`; a PharmGKB module
  adds `pharm_variants.csv`. A module **never** carries an empty `variants.csv` or a foreign domain's
  columns just to host one table — the SNP core stays minimal (see CLAUDE.md, the human-authorable
  gate).
- **Data-agnostic.** A module is a declarative lookup; it contains **no measurement**. The measured
  quantity (activity score, copy number, repeat count, heteroplasmy fraction) is supplied by the
  **consumer** at query time. The table never sees a sample.
- **Binning is uniform and inclusive.** Every quantity table shares one column vocabulary
  (`measure_kind, measure_min, measure_max, direction, clin_sig, phenotype, trait_efo_id, conclusion,
  unresolved`) plus its explicit key columns. Ranges are inclusive `[measure_min, measure_max]`:
  `min == max` is a *sharp* value, `min < max` a range, `measure_max` empty is open-ended. A row with
  `unresolved=true` is the sentinel a consumer selects when the measurement is absent (T1) — it
  carries no bounds, and is **never** the reference/lowest bin.

Contents: (1) simple SNV — needs **none** of the machinery; (2) APOE diplotype; (3) G6PD hemizygous;
(4) mitochondrial homoplasmic + heteroplasmy; (5) SMN1 copy-number dosage; (6) CYP2D6 star-alleles +
activity; (7) HTT repeat expansion; (8) PGS declaration; (9) PharmGKB drug response; (10) general
annotation axes on `VariantRow`.

---

## 1. Simple SNV module — needs none of the below

Most modules are just this: one row per genotype at a locus, on the existing `variants.csv`. The
0.3 column additions (`direction`, `stat_significance`, `effect_allele`, `trait_efo_id`, `clin_sig`)
are all optional; a simple module ignores diplotypes, copy number, and star-alleles entirely.

```csv
rsid,genotype,effect_allele,direction,stat_significance,gene,phenotype,trait_efo_id,conclusion
rs1801133,T/T,T,risk,significant,MTHFR,Homocysteine,EFO_0004518,"677 TT — reduced enzyme activity"
rs1801133,C/T,T,risk,suggestive,MTHFR,Homocysteine,EFO_0004518,"677 CT — intermediate"
rs1801133,C/C,C,neutral,not_significant,MTHFR,Homocysteine,EFO_0004518,"677 CC — normal"
```

---

## 2. APOE ε2/ε3/ε4 — diplotype (SV-free degenerate PGx case)

`haplotypes.csv` (`HaplotypeRow` — junction, one row per haplotype×variant):
```csv
haplotype_name,rsid,allele,gene
e2,rs429358,T,APOE
e2,rs7412,T,APOE
e3,rs429358,T,APOE
e3,rs7412,C,APOE
e4,rs429358,C,APOE
e4,rs7412,C,APOE
```
`diplotypes.csv` (`DiplotypeRow` — canonicalized `haplotype_a <= haplotype_b`, multiple rows per pair
for **pleiotropy**: ε2/ε2 protective for AD, risk for hyperlipoproteinemia).
**Contract (C3):** the pair is stored **lexicographically-sorted** on the star-string (so `*10 < *2`,
because `'1' < '2'`); a consumer MUST sort identically before lookup, or it silently misses the row —
do not sort star-alleles numerically.
```csv
gene,haplotype_a,haplotype_b,trait_efo_id,direction,clin_sig,phenotype,conclusion
APOE,e2,e2,EFO_0000249,protective,protective,Late-onset Alzheimer's,"ε2/ε2 — reduced LOAD risk"
APOE,e3,e4,EFO_0000249,risk,risk_factor,Late-onset Alzheimer's,"ε3/ε4 — ~3x risk"
APOE,e4,e4,EFO_0000249,risk,risk_factor,Late-onset Alzheimer's,"ε4/ε4 — ~12–15x risk"
APOE,e2,e2,EFO_0004749,risk,risk_factor,Type III hyperlipoproteinemia,"ε2/ε2 — dysbetalipoproteinemia predisposition"
```
Unphased `rs429358=C/T, rs7412=C/T` is formally ε4/ε2 *or* ε1/ε3 — the consumer's caller enumerates
pairs of *defined* haplotypes; ε1 undefined ⇒ resolves to ε4/ε2. No author logic. *(Per-study effect
axes — `effect_size`/`effect_measure`/`stat_significance` — are a round-2 extension; the sample
`DiplotypeRow` carries the orthogonal `direction`/`clin_sig` axes only.)*

---

## 3. G6PD — X-linked hemizygous (0.3 item 5b: single-allele genotype)

The author enumerates **both cardinalities**; the consumer matches the sample's allele count
(1 for a male's X, 2 for a female's). The single-allele row is what item 5b enables.
```csv
rsid,chrom,genotype,direction,clin_sig,gene,phenotype,trait_efo_id,conclusion
rs5030868,X,T,risk,pathogenic,G6PD,G6PD deficiency,MONDO_0009905,"Hemizygous deficient (1 X copy)"
rs5030868,X,T/T,risk,pathogenic,G6PD,G6PD deficiency,MONDO_0009905,"Homozygous deficient"
rs5030868,X,C/T,risk,pathogenic,G6PD,G6PD deficiency,MONDO_0009905,"Heterozygous — intermediate (mosaic)"
rs5030868,X,C/C,neutral,benign,G6PD,G6PD deficiency,MONDO_0009905,"Normal"
```
(The drug-trigger meaning — haemolysis on oxidative drugs — is the PGx `drug`/`response` layer.)

---

## 4. Mitochondrial — homoplasmic (0.3 item 5b) + heteroplasmy (0.4 `heteroplasmy.csv`)

Homoplasmic is reachable via a single-allele genotype on `variants.csv`; heteroplasmy is a
`HeteroplasmyRow` binning table keyed on `(gene, reference_sequence)` — the reference accession is
part of the key because rCRS/`NC_012920` vs legacy `NC_001807` disagree and `genome_build` does not
disambiguate.

Homoplasmic (`variants.csv`):
```csv
rsid,chrom,start,genotype,direction,clin_sig,gene,phenotype,trait_efo_id,conclusion
,MT,3243,G,risk,pathogenic,MT-TL1,MELAS,MONDO_0010789,"Homoplasmic m.3243A>G"
```
Heteroplasmy (`heteroplasmy.csv`, `measure_kind=allele_fraction`, bounds in `[0,1]`). `tissue` is
optional but load-bearing — **bins are tissue-conditional** (a blood fraction under-represents the
affected-tissue burden), so tissue is part of the key. `source_field=AF` binds the measure to the VCF
(e.g. Mutect2-mito `FORMAT/AF`). `reference_sequence` rejects the legacy `NC_001807` lineage (it yields
a confidently-wrong haplogroup); use `NC_012920.1` (rCRS).
```csv
gene,reference_sequence,tissue,source_field,measure_kind,measure_min,measure_max,direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved
MT-TL1,NC_012920.1,blood,AF,allele_fraction,0.8,1.0,risk,pathogenic,MELAS,MONDO_0010789,"high heteroplasmy (blood) — symptomatic",false
MT-TL1,NC_012920.1,blood,AF,allele_fraction,0.1,0.8,neutral,uncertain_significance,MELAS,MONDO_0010789,"low-level (blood) — usually subclinical",false
MT-TL1,NC_012920.1,blood,AF,allele_fraction,,,,,,,"caller artifact rejected — not called",true
```
A two-allele genotype on `MT` still raises the item-5b guardrail warning (MT is not diploid).

---

## 5. SMN1 — whole-gene copy-number dosage (0.4 `copynumbers.csv`)

`CopyNumberRow`, keyed on `gene`. A sharp dosage is `measure_min == measure_max` (0 copies = `[0,0]`);
`3+` is `measure_min=3` with an empty `measure_max`. SMA severity depends on **SMN1 and SMN2** copy
number, so SMN2 rides in the explicit `modifier_gene`/`modifier_cn` columns (multicolumn keying —
never a packed tuple). Single-gene rows leave the modifier null.
```csv
gene,measure_kind,measure_min,measure_max,modifier_gene,modifier_cn,direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved
SMN1,copy_number,0,0,SMN2,3,risk,pathogenic,Spinal muscular atrophy,MONDO_0001516,"0 SMN1 / 3 SMN2 — milder",false
SMN1,copy_number,0,0,SMN2,1,risk,pathogenic,Spinal muscular atrophy,MONDO_0001516,"0 SMN1 / 1 SMN2 — severe",false
SMN1,copy_number,1,1,,,risk,pathogenic,Spinal muscular atrophy,MONDO_0001516,"1 copy — carrier",false
SMN1,copy_number,2,2,,,neutral,benign,Spinal muscular atrophy,MONDO_0001516,"2 copies — normal",false
SMN1,copy_number,3,,,,neutral,benign,Spinal muscular atrophy,MONDO_0001516,"3+ copies — normal",false
SMN1,copy_number,,,,,,,Spinal muscular atrophy,MONDO_0001516,"CN not resolved (seg-dup ~20×) — needs MLPA",true
```
Inert until a consumer supplies a CNV call. There is no `copy_number` column — a sharp value is
`measure_min == measure_max`.

---

## 6. CYP2D6 — star-alleles + activity score (the hard PGx case)

The star-string is the **canonical allele-unit identity** (stored verbatim); `copy_number`/`sv_type`/
`hybrid_orientation` are optional parsed conveniences of the *cis* allele-unit. Phenotype is computed
by the **consumer** as `activity_score = Σ activity(allele_i) × copies_i` over the two phased
allele-units, then binned.

`allele_function.csv` (`AlleleFunctionRow` — allele-unit → activity value + CPIC function category):
```csv
gene,allele,activity_value,function_status,suballele,copy_number,sv_type,hybrid_orientation
CYP2D6,*1,1.0,normal_function,,,,
CYP2D6,*2,1.0,normal_function,,,,
CYP2D6,*4,0.0,no_function,,,,
CYP2D6,*4.001,0.0,no_function,4.001,,,
CYP2D6,*5,0.0,no_function,,,deletion,
CYP2D6,*10,0.25,decreased_function,,,,
CYP2D6,*1x2,2.0,increased_function,,2,duplication,
CYP2D6,*36+*10,0.25,decreased_function,,,,*36+*10
```
`activity_phenotype.csv` (`ActivityPhenotypeRow` — per-gene binning; DATA, editable by consensus, so
the 2019 CPIC threshold shift is a data edit, not a code change):
```csv
gene,measure_kind,measure_min,measure_max,direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved
CYP2D6,activity_score,0,0,,,Poor Metabolizer,,"AS 0 — PM",false
CYP2D6,activity_score,0.25,1.0,,,Intermediate Metabolizer,,"AS 0.25–1 — IM",false
CYP2D6,activity_score,1.25,2.25,,,Normal Metabolizer,,"AS 1.25–2.25 — NM",false
CYP2D6,activity_score,2.5,,,,Ultrarapid Metabolizer,,"AS ≥2.5 — UM",false
CYP2D6,activity_score,,,,,,,"no diplotype resolved (e.g. Cyrius Genotype=None) — unresolved, NOT Normal",true
```
Why a consumer (star-allele caller: Aldy/Cyrius/PharmCAT) is required: **copy number attaches to a
specific cis allele**, so `*2x2/*4` (AS 2 → NM) ≠ `*2/*4x2` (AS 1 → IM) — same variants and total
copy number, different phenotype. The format supplies the tables; the caller supplies the phased
diplotype + CN/SV. The `unresolved` row is the safety property: no diplotype ⇒ *unresolved*, never
"Normal Metabolizer".

---

## 7. HTT — repeat expansion (0.4 `repeat_alleles.csv`)

`RepeatAlleleRow`, keyed on `(gene, repeat_unit)` — the motif is part of the identity (T3): a repeat
count is only comparable within its motif definition. The count is a **consumer** call
(ExpansionHunter / adVNTR / a span genotyper) that must state the motif it counted. `source_field=REPCN`
binds the measure to an ExpansionHunter VCF (`INFO/RU` → `repeat_unit`, `FORMAT/REPCN` → the count) —
consumable with zero glue. **Author the reference (`≤26 normal`) bin** so every count hits exactly one
bin; `validate_bins()` rejects overlaps and warns on interior gaps.
```csv
gene,repeat_unit,source_field,measure_kind,measure_min,measure_max,direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved
HTT,CAG,REPCN,repeat_count,40,,risk,pathogenic,Huntington disease (full penetrance),MONDO_0007739,"≥40 CAG — fully penetrant",false
HTT,CAG,REPCN,repeat_count,36,39,risk,pathogenic,Huntington disease (reduced penetrance),MONDO_0007739,"36–39 CAG — reduced penetrance",false
HTT,CAG,REPCN,repeat_count,27,35,neutral,uncertain_significance,Intermediate allele,MONDO_0007739,"27–35 CAG — intermediate",false
HTT,CAG,REPCN,repeat_count,6,26,neutral,benign,Normal,MONDO_0007739,"≤26 CAG — normal",false
HTT,CAG,REPCN,repeat_count,,,,,,,"repeat not spanned on short reads (CI) — unresolved",true
```
Notes: **`repeat_unit` is free-form** (large composite VNTR motifs like DRD4 exon-3 ~48 bp and DAT1
~40 bp are real, not `CAG`-style trinucleotides — warn, never reject, on non-`[ACGTN]`). Bounds are
`float` because **half-repeats are real** (MAOA-uVNTR 3.5R). Forensic STR **microvariant** notation
(`TH01 9.3` = "9 repeats + 3 bases", not decimal 9.3) is an allele-*name* convention, not a binning
bound — for pathogenic-threshold loci (HTT) it never matters; for forensic STRs, carry the exact
allele string in the reserved motif-path escape hatch, not the float bound. **5-HTTLPR does not belong
here — and does not fit 0.4 at all yet.** It is a biallelic **S/L structural indel** (a ~43 bp
insertion), not a repeat *count*; and its `S`/`L` alleles are **not nucleotides**, so neither
`VariantRow.genotype` nor `HaplotypeRow.allele` (both `^[ACGT]+$`) can express them. This is the
concrete motivating case for **RM5 (symbolic alleles**, `<S>`/`<L>`/`<DEL>`) — a deferred gap, not a
today-authorable shape. (It is usually read phased with `rs25531`, so it is really a mini-diplotype
over a symbolic allele.)
The complex-VNTR motif-path form (DAT1 `A-A-B-C-D-…`) is reserved as the home for the sanctioned
declarative-grammar escape hatch (a regex over an allele string) if a plain count proves too coarse.

---

## 8. PGS — polygenic score declaration (0.4 `pgs.csv`)

`PgsRow` — a **manifest of PGS Catalog IDs, not authored weights** (a declared interface, like
`GenePanelSpec`, not a binning table). The ancestry-validity fields are the anti-misuse guardrail: a
consumer refuses or caveats an out-of-ancestry application instead of silently miscalibrating.
```csv
pgs_id,trait_efo_id,note,group,training_ancestry,training_cohort,match_rate_floor,research_tier
PGS000135,EFO_0000692,"Schizophrenia (EUR-derived)",psychiatric,EUR,,0.8,research_only
PGS000765,EFO_0001645,"Coronary artery disease",cardiometabolic,EUR,"UK Biobank NW-EUR",0.8,research_only
```
`research_tier=research_only` pins as *data* that a PRS is a Z/percentile *within a matched reference
distribution*, never an ancestry-calibrated absolute risk; `training_ancestry` (superpop floor) +
optional `training_cohort` (sub-superpop precision) let a consumer withhold or caveat the score
off-population; **`match_rate_floor`** is the author-set variant-match floor below which the score is
invalid. The *observed* per-sample match rate is a measurement — it lives consumer-side, never in the
module (the data-agnostic north star).

---

## 9. PharmGKB drug response (item 9) — a distinct table, not columns on `VariantRow`

Drug-response annotation maps a variant/diplotype → a **drug** → a **response** + a PharmGKB
**evidence level** (`1A`…`4`) — a different axis from a risk weight. It gets its **own** rowtype so a
SNP author's `variants.csv` never grows drug columns (one CSV = one concern).

Single-variant PharmGKB (`pharm_variants.csv`, `PharmVariantRow` — VKORC1 → warfarin):
```csv
rsid,gene,drug,response,evidence_level,trait_efo_id,conclusion
rs9923231,VKORC1,warfarin,"reduced dose requirement",1A,,"−1639 A — lower warfarin dose"
rs1799853,CYP2C9,warfarin,"reduced clearance",1A,,"*2 — lower warfarin dose"
```
Diplotype-keyed PharmGKB rides on `DiplotypeRow`'s optional `drug`/`response`/`evidence_level` (it is
already a PGx-domain table a SNP author never opens):
```csv
gene,haplotype_a,haplotype_b,trait_efo_id,phenotype,drug,response,evidence_level,conclusion
CYP2D6,*1,*4,,Intermediate Metabolizer,codeine,"reduced analgesia",1A,"*1/*4 — impaired codeine activation"
```
A PharmGKB module carries `pharm_variants.csv` (+ the diplotype tables if star-allele) and **no**
`variants.csv`.

---

## 10. General annotation axes on `VariantRow` (optional, sparse)

Three optional refinements apply to *any* variant finding, so they live on `VariantRow` (not a domain
table); a plain SNP row omits them entirely.
```csv
rsid,genotype,gene,clin_sig,requires_callable,acmg_sf,actionability,conclusion
rs80357906,A/AT,BRCA1,pathogenic,true,true,preventable,"BRCA1 frameshift — HBOC; risk-reducing options"
```
- `requires_callable=true` — the *absence* of this variant is the informative call; a consumer lacking
  callability data must withhold the "no pathogenic variant" reassurance, never assert it.
- `acmg_sf=true` — the gene is on the ACMG secondary-findings list.
- `actionability=preventable` — an `ACTIONABILITY_SEED` value a consumer's return-of-results policy may
  read; the format never decides disclosure.
