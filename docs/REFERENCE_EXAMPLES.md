# Reference examples — worked module drafts

These are **hand-authored sketches** of how modules are expressed with the 0.3/0.4 features (see
[ROADMAP.md](ROADMAP.md), [PROPOSAL_0_4.md](PROPOSAL_0_4.md)). They are **ideas and drafts for module
authors and consumers** — a picture of the intended shapes. Column sets, vocab, and file names may
still change during the 0.4 round-2 vetting. rsIDs / coordinates / effect sizes are illustrative.

**The 0.4 relational/quantitative tables in §2, §4–§8 are now schema-validated** by the sample
implementation in `just_dna_format.{binning,pgx,pgs}` (see `schema/tests/test_v04.py`). Every CSV row
below round-trips through its Pydantic model. The compiler does **not** yet materialize them into
parquet — that is deferred until the shapes freeze (PROPOSAL_0_4).

**Two conventions the sample settled:**
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
activity; (7) HTT repeat expansion; (8) PGS declaration.

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
for **pleiotropy**: ε2/ε2 protective for AD, risk for hyperlipoproteinemia):
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
Heteroplasmy (`heteroplasmy.csv`, `measure_kind=allele_fraction`, bounds in `[0,1]`):
```csv
gene,reference_sequence,measure_kind,measure_min,measure_max,direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved
MT-TL1,NC_012920.1,allele_fraction,0.8,1.0,risk,pathogenic,MELAS,MONDO_0010789,"high heteroplasmy — symptomatic",false
MT-TL1,NC_012920.1,allele_fraction,0.1,0.8,neutral,uncertain_significance,MELAS,MONDO_0010789,"low-level — usually subclinical",false
MT-TL1,NC_012920.1,allele_fraction,,,,,,,"caller artifact rejected — not called",true
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
(ExpansionHunter / adVNTR / a span genotyper) that must state the motif it counted.
```csv
gene,repeat_unit,measure_kind,measure_min,measure_max,direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved
HTT,CAG,repeat_count,40,,risk,pathogenic,Huntington disease (full penetrance),MONDO_0007739,"≥40 CAG — fully penetrant",false
HTT,CAG,repeat_count,36,39,risk,pathogenic,Huntington disease (reduced penetrance),MONDO_0007739,"36–39 CAG — reduced penetrance",false
HTT,CAG,repeat_count,27,35,neutral,uncertain_significance,Intermediate allele,MONDO_0007739,"27–35 CAG — intermediate",false
HTT,CAG,repeat_count,6,26,neutral,benign,Normal,MONDO_0007739,"≤26 CAG — normal",false
HTT,CAG,repeat_count,,,,,,,"repeat not spanned on short reads (CI) — unresolved",true
```
The complex-VNTR motif-path form (DAT1 `A-A-B-C-D-…`) is reserved as the home for the sanctioned
declarative-grammar escape hatch (a regex over an allele string) if a plain count proves too coarse —
not built here.

---

## 8. PGS — polygenic score declaration (0.4 `pgs.csv`)

`PgsRow` — a **manifest of PGS Catalog IDs, not authored weights** (a declared interface, like
`GenePanelSpec`, not a binning table). The ancestry-validity fields are the anti-misuse guardrail: a
consumer refuses or caveats an out-of-ancestry application instead of silently miscalibrating.
```csv
pgs_id,trait_efo_id,note,group,training_ancestry,match_rate,research_tier
PGS000135,EFO_0000692,"Schizophrenia (EUR-derived)",psychiatric,EUR,0.94,research_only
PGS000765,EFO_0001645,"Coronary artery disease",cardiometabolic,EUR|EAS,0.88,research_only
```
`research_tier=research_only` pins as *data* that a PRS is a Z/percentile *within a matched reference
distribution*, never an ancestry-calibrated absolute risk; `training_ancestry` lets a consumer
withhold or caveat the score off-population; `match_rate` is the variant-match floor below which the
score is invalid.
