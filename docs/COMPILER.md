# Compiler coverage of the 0.3 schema

`just-dna-compiler` adopts the 0.3 schema (`docs/ROADMAP.md` → *Planned for 0.3*) with a
**C++-standard-style partial-conformance** stance: the **validator is complete** (every 0.3 column
and vocabulary is fully validated), while some **computed** items are **intentionally
unimplemented** for now and listed explicitly below — the way a C++ standard-library release ships a
feature-coverage table rather than all-or-nothing conformance.

This split is deliberate. Validation is cheap, self-contained, and has no consumer dependency, so it
ships in full. The deferred items are *computations* (derivations, phase preservation, new stats)
that either belong to the cross-repo migration flow or have no consumer yet — building them now would
be speculative. Reference consumer semantics: just-dna-lite (`just_dna_pipelines`) derives direction
from `state`/`weight` and tokenizes ClinVar CLNSIG; our columns are the explicit, validated form of
those.

## Coverage table

| 0.3 feature | Validated | Materialized (→ parquet) | Computed / derived | Status |
|---|---|---|---|---|
| `direction` (`VariantRow`) | ✅ full vocab | ✅ `weights.parquet` | ⛔ not derived from `state`/`weight` | validate + passthrough |
| `stat_significance` (`VariantRow`, `StudyRow`) | ✅ full vocab | ✅ | ⛔ not derived from `p_value` | validate + passthrough |
| `effect_size` (`VariantRow`, `StudyRow`) | ✅ float | ✅ | — | complete |
| `effect_measure` (`VariantRow`, `StudyRow`) | ✅ permissive (open) | ✅ | — | complete (intentionally open) |
| `effect_allele` (`VariantRow`) | ✅ nucleotides | ✅ | ⛔ no strand/ref reconciliation | validate + passthrough |
| `flags` (`VariantRow`) | ✅ open; split; reserved set | ✅ `List[str]` | ✅ unknown-tag INFO (`ValidationResult.info`) | complete |
| `trait_efo_id` (`VariantRow`, `StudyRow`) | ✅ CURIE(s) | ✅ | — | complete |
| `clin_sig` (`VariantRow`) | ✅ full vocab | ✅ | ⛔ `pathogenic`/`benign` booleans not synced | validate + passthrough |
| genotype widening: hemizygous single allele | ✅ | ✅ (1-element list) | — | complete |
| genotype widening: phased `A\|G` | ✅ (order kept, not sorted) | ⚠️ allele list only — **phase separator not preserved** | ⛔ | validate; phase materialization deferred |
| `state` (legacy) | ✅ (unchanged, required) | ✅ (unchanged) | ⛔ not turned into a `direction` alias | unchanged |
| MT / non-diploid genotype | ✅ warning on a two-allele MT genotype | — | — | complete |
| direction/weight sign consistency | ✅ warning | — | — | complete |

## Intentionally unimplemented (computed) — and why

1. **`state → direction`/`stat_significance` derivation (back-population).** The upgrade migration
   that fills the new columns from the legacy `state` belongs to the marketplace
   `revalidate`/`needs_upgrade` drift flow, not the bare compiler. The compiler *validates* both, but
   does not compute one from the other.
2. **`clin_sig` ↔ `pathogenic`/`benign` synchronization.** Both are validated and materialized
   independently; the compiler does not derive the booleans from `clin_sig` (or vice versa).
3. **Phase preservation in the artifact.** A phased `A|G` is accepted and validated, but
   `weights.parquet` stores an allele *list* (`["A","G"]`), so the `|`-vs-`/` distinction is lost;
   the reverse writer re-emits a sorted unphased genotype. Phased matching is a 0.4 concern.
4. **New computed manifest stats.** `Stats` still carries the 0.2 counts
   (`clinvar_count`/`pathogenic_count`/`benign_count`); no new distributions (e.g. by `direction` or
   `clin_sig`) are computed.
5. **All of 0.4** — diplotype/haplotype, copy-number, PGx activity scores — is out of scope here (new
   file kinds, consumer-gated).

## Consequences worth knowing

- **`weights.parquet`/`studies.parquet` now carry the 0.3 columns** (null-filled when unused), so a
  re-compile under this compiler changes `artifact.digest` for every module — even one that sets no
  0.3 column. That is expected on a compiler-version bump: reproducibility is pinned by
  `compiler_version`, and already-published versions keep their old digest until re-published.
- **Round-trip (`reverse_module` → recompile) does not preserve phase** (item 3) and re-sorts
  two-allele genotypes; every other 0.3 column round-trips.
- The **`ValidationResult.info`** channel is new (additive) — it carries non-reserved `flags` notes,
  using stdlib logging semantics, **not** Eliot (the format packages do not depend on Eliot).

Tests: `compiler/tests/test_v03.py` exercises the complete validator, the genotype widening, the
warnings/INFO, and the materialization passthrough.
