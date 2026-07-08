# Reference examples — worked module drafts (illustrative, not normative)

These are **hand-authored sketches** of how modules *could* be expressed once the planned 0.3/0.4
features land (see [ROADMAP.md](ROADMAP.md)). They are **ideas and drafts for module authors and
consumers** — a picture of the intended shapes — **not a shipped contract**. Column sets, vocab, and
file names may change during the 0.4 vetting. rsIDs / coordinates / effect sizes are illustrative.

They exist because worked examples caught real design bugs (e.g. the diplotype key needing
`trait_efo_id`), and because a consumer implementing calling/matching benefits from seeing the target
shape early.

Contents: (1) a simple SNV module — the common case that needs **none** of the advanced machinery;
(2) APOE diplotype (0.4 relational); (3) G6PD hemizygous X-linked (0.3 item 5b); (4) mitochondrial
homoplasmic (0.3 item 5b) vs heteroplasmic (reserved); (5) SMN1 copy-number dosage (0.4 item 7b);
(6) CYP2D6 star-alleles + activity score (0.4 PGx, the hard case).

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

## 2. APOE ε2/ε3/ε4 — diplotype (0.4 relational; SV-free degenerate case)

`haplotypes.csv`:
```csv
haplotype_name,rsid,allele
e2,rs429358,T
e2,rs7412,T
e3,rs429358,T
e3,rs7412,C
e4,rs429358,C
e4,rs7412,C
```
`diplotypes.csv` — key `(haplotype_a, haplotype_b, trait_efo_id)`, canonicalized `a <= b`, multiple
rows per pair for **pleiotropy** (ε2/ε2 protective for AD, risk for hyperlipoproteinemia):
```csv
haplotype_a,haplotype_b,trait_efo_id,phenotype,direction,stat_significance,effect_size,effect_measure,flags,conclusion
e2,e2,EFO_0000249,Late-onset Alzheimer's,protective,significant,0.6,OR,,"ε2/ε2 — reduced LOAD risk"
e3,e4,EFO_0000249,Late-onset Alzheimer's,risk,significant,3.2,OR,,"ε3/ε4 — ~3x risk"
e4,e4,EFO_0000249,Late-onset Alzheimer's,risk,significant,14.9,OR,,"ε4/ε4 — ~12–15x risk"
e2,e4,EFO_0000249,Late-onset Alzheimer's,neutral,suggestive,,,pleiotropic,"ε2/ε4 — opposing alleles"
e2,e2,EFO_0004749,Type III hyperlipoproteinemia,risk,suggestive,,,pleiotropic,"ε2/ε2 — dysbetalipoproteinemia predisposition"
```
Unphased `rs429358=C/T, rs7412=C/T` is formally ε4/ε2 *or* ε1/ε3 — the consumer's caller enumerates
pairs of *defined* haplotypes; ε1 undefined ⇒ resolves to ε4/ε2. Define ε1 ⇒ ambiguous, and the
`phased` flag marks phase-dependent rows. No author logic.

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
(The drug-trigger meaning — haemolysis on oxidative drugs — is the PGx `drug`/`response` layer, §6.)

---

## 4. Mitochondrial — homoplasmic (0.3 item 5b) vs heteroplasmic (reserved)

Homoplasmic is reachable now via a single-allele genotype; **heteroplasmy is not** — a mutant
*fraction* needs the reserved `allele_fraction` + a penetrance threshold (deferred).
```csv
rsid,chrom,start,genotype,direction,clin_sig,gene,phenotype,trait_efo_id,conclusion
,MT,3243,G,risk,pathogenic,MT-TL1,MELAS,MONDO_0010789,"Homoplasmic m.3243A>G"
# heteroplasmic (NOT yet expressible): needs allele_fraction=0.30 + threshold — reserved
```
A two-allele genotype on `MT` should raise the item-5b guardrail warning (MT is not diploid).

---

## 5. SMN1 — whole-gene copy-number dosage (0.4 item 7b `copynumbers.csv`)

Conclusion is a function of **copy number alone**, no allele identity / no genotype — a distinct row
shape from `VariantRow`. (Distinct from CYP2D6, where copy number attaches to a *specific* allele.)
```csv
gene,copy_number,direction,clin_sig,phenotype,trait_efo_id,conclusion
SMN1,0,risk,pathogenic,Spinal muscular atrophy,MONDO_0001516,"0 copies — affected (SMA)"
SMN1,1,risk,pathogenic,Spinal muscular atrophy,MONDO_0001516,"1 copy — carrier"
SMN1,2,neutral,benign,Spinal muscular atrophy,MONDO_0001516,"2 copies — normal"
SMN1,3,neutral,benign,Spinal muscular atrophy,MONDO_0001516,"3+ copies — normal"
```
Inert until a consumer supplies a CNV call.

---

## 6. CYP2D6 — star-alleles + activity score (0.4 PGx, the hard case)

The star-string is the **canonical allele-unit identity** (stored verbatim); `sv_type`/`copy_number`
are optional parsed conveniences. Phenotype is computed by the **consumer** as
`activity_score = Σ activity(allele_i) × copies_i` over the two phased allele-units, then binned.

`allele_function.csv` (allele-unit → activity value + function):
```csv
allele,gene,activity_value,function,defining_note
*1,CYP2D6,1.0,normal,reference
*2,CYP2D6,1.0,normal,
*4,CYP2D6,0.0,no_function,rs3892097 (core)
*5,CYP2D6,0.0,no_function,whole-gene deletion (SV)
*10,CYP2D6,0.25,decreased,rs1065852
*36+*10,CYP2D6,0.25,decreased,tandem hybrid — one cis allele-unit
```
`activity_phenotype.csv` (per-gene binning — DATA, editable by consensus):
```csv
gene,score_min,score_max,phenotype
CYP2D6,0,0,Poor Metabolizer
CYP2D6,0.25,1.0,Intermediate Metabolizer
CYP2D6,1.25,2.25,Normal Metabolizer
CYP2D6,2.5,,Ultrarapid Metabolizer
```
Why a consumer (star-allele caller: Stargazer `dip_score`/`phenotype`/`hap*_sv`; PyPGx
`Genotype`/`CNV`/`AlternativePhase`; Aldy `Major`/`Copy`) is required: **copy number attaches to a
specific cis allele**, so `*2×2/*4` (AS 2 → NM) ≠ `*2/*4×2` (AS 1 → IM) — same variants and same
total copy number, different phenotype. The format supplies the tables; the caller supplies the
phased diplotype + CN/SV. For SV/duplication/unphased cases a `diplotypes.csv` enumeration is the
safe canonical fallback (as CPIC ships).
