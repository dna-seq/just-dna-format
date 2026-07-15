# Agent Guidelines — just-dna-format

This repo is a **uv workspace** publishing two libraries: **`just-dna-format`** (the schema contract
— pydantic models for the authored spec DSL and the compiled `manifest.json`, plus integrity/
identity helpers, costing only `pydantic` + `cryptography` — the latter solely for Ed25519 signing) and **`just-dna-compiler`** (the reference compiler that
transforms a validated spec into a multi-parquet artifact + manifest — the three-parquet SNP core
plus one parquet per optional table kind a composed module adds, adding polars/duckdb). Any
consumer picks the tier it needs. There is **no app, no orchestration, and no network here** — those
live in `just-dna-pipelines` / `just-dna-lite` / `just-dna-marketplace`.

## Read these first, in this order

1. **[docs/CONSTITUTION.md](docs/CONSTITUTION.md) — the durable charter. READ IT BEFORE JUDGING OR
   CHANGING ANYTHING.** It is the source of truth for what these packages are, what they will never
   do, and the invariants every release upholds (declarative-not-code, no network, backward-compat
   within a major, integrity-as-identity, orthogonal axes, the vocabulary idiom, round-trip/
   idempotency, and requiredness compatibility). When a plan conflicts with it, it wins. **An audit
   or design review that has not read the Constitution is incomplete** — its compatibility rules
   (Principles 3, 7, 8) decide whether a proposed change is even legal. **The charter is
   self-contained — it names no other document.** The navigation *into* the living material it
   alludes to is here in this guide (below); keep it that way — never add an outward pointer to the
   Constitution.
2. **[docs/ROADMAP.md](docs/ROADMAP.md)** — forward-only, revised often. Holds the 0.5 scope (`RMn`
   items), the freeform idea-book, **the reserved-namespace tracker** (Constitution Principle 5), and
   **the 1.0-cleanup candidate tracker** (Principles 3 and 8). These two trackers are the concrete,
   living lists the Constitution keeps out of itself.
3. **[docs/CHANGELOG.md](docs/CHANGELOG.md)** — what actually shipped, newest first (shared across the
   ecosystem repos that consume these libs).
4. **[docs/COMPILER.md](docs/COMPILER.md)** — the compiler's per-feature coverage table (which schema
   features are validated / materialized / computed).

## The design cycle (the order of things)

Feature ideas move through **one loop**; the docs are its stages, and a design task should walk them
in order rather than jumping to code:

1. **Feedback** — a consumer's field report → [docs/CONSUMER_FIELD_NOTES.md](docs/CONSUMER_FIELD_NOTES.md),
   [docs/CONSUMER_ROUND2_AND_0_5.md](docs/CONSUMER_ROUND2_AND_0_5.md)
2. **Usage → blockers → solvability** — run each use case against the current bricks: *enabled*,
   *consumer-side* (the format owns nothing), or a *gap* closable additively? →
   [docs/USE_CASES.md](docs/USE_CASES.md)  ← **start a design task here**
3. **Means → draft schema → decision** — the proposed shape + charter check + open questions →
   [docs/PROPOSAL_0_4.md](docs/PROPOSAL_0_4.md)
4. **Conclusion — how to author it now, with these bricks** → [docs/REFERENCE_EXAMPLES.md](docs/REFERENCE_EXAMPLES.md)
5. **Terminal** — either **shipped** (schema + compiler; recorded in COMPILER.md coverage) **or**
   **deferred** (a recognised gap parked as an `RMn` roadmap item in ROADMAP.md).

`USE_CASES.md` and `REFERENCE_EXAMPLES.md` are the **same use cases at two points in the loop** —
questions (what blocks?) vs answers (author it like this). A blocker is never a dead end: it is
dissolved (was consumer-side), closed additively, or explicitly parked. See *The feedback → schema
cycle* in `USE_CASES.md`.

## Coding standards

- **Dependency tiers are sacred** (CONSTITUTION Goal 2): never add a heavy dep to `just-dna-format`;
  the compiler's polars/duckdb stay in `just-dna-compiler`. Never pull Dagster / LLM SDKs / HF.
- **No network, inject-only** (Principle 2): the resolver never downloads; the caller injects any
  reference.
- **Data-agnostic — a north star, not a totality claim.** A module and its compiled artifact are
  pure *annotation*: lookup tables and bounded rules mapping a quantity/genotype to a phenotype. They
  carry **no sample data, no genotype under test, no measured value** — the measurement is supplied by
  the consumer at query time (the format supplies the table; the consumer supplies the call). *But*
  the pydantic schemas are a **generalization over a practical subset** of real data items — concrete
  loci, callers, and realistic value ranges — i.e. an implicit data model with an untracked empirical
  footprint, not an all-encompassing universal one. Be explicit that a shape generalizes known cases
  rather than pretending it covers everything: when a real data item doesn't fit, that is a schema gap
  to widen *additively*, not a consumer error. (This is why `copy_number`-as-a-measured-value was
  wrong — the module never holds the measurement — yet the *range* shapes are still only as general as
  the cases they were generalized from.)
- **Human-authorable ⇔ machine-precise — a gate on every schema change.** The authored DSL
  (`module_spec.yaml` + CSVs) is a *duality*: it must be **both** a legible, human-authorable artifact
  **and** a formally algorithmizable, machine-precise one. The compiled parquet is already the
  pure-machine form — **if we only wanted machine precision we would ship parquet-only.** The DSL
  exists for the human. So gate any schema change on: **"will this burden the rare human author?"**
  Modules must never read like enterprise-DB internals — alien, sprawling, machine-code-like. Corollary
  — **one CSV = one concern; compose from optional table kinds**: the SNP core (`variants.csv` +
  `studies.csv`) stays minimal; a module includes only the table kinds it uses; a PGx / PharmGKB / PRS
  module adds its own focused table (`diplotypes.csv`, `pharm_variants.csv`, `pgs.csv`) rather than an
  empty `variants.csv` or a foreign domain's columns on every row. When human-legibility and
  machine-precision tension, the parquet absorbs the precision; the DSL keeps the human shape.
- Type hints mandatory; **pathlib** for paths; **absolute imports only**; **no inline imports** (a
  guarded module-level `try/except ImportError` for optional deps is the only exception).
- Pydantic 2 for all data models. Constrained vocabularies are `frozenset[str]` + a validator, never
  `Enum`/`Literal` (Principle 6).
- **Authored row models inherit `AuthoredModel`** (`just_dna_format.base`), never `BaseModel` directly.
  It carries the reserved-namespace guard (`extra="forbid"` + the `reject_reserved` before-validator)
  and the shared field validators (`rsid`/`trait_efo_id`/`direction`/`clin_sig`/`stat_significance`/
  `evidence_level`/finite-`effect_size`). Don't re-declare `model_config` or re-copy those validators
  per model (that per-model duplication is the anti-pattern being unwound); when a validator is
  identical across ≥2 models, move it onto the base with `check_fields=False`. Keep only field-specific
  rules on each model.
- **The reserved namespace (`vocab.RESERVED_NAMES_0_4`) is only for names expected to become real
  module columns later** (Principle 5) — *not* a catalogue of barred names. `extra="forbid"` already
  rejects any unknown/misspelled column generically, so barring a specific non-feature is arbitrary
  (barring `caller` is as pointless as barring `pasta_recipe`). Before reserving a name, ask: *will a
  release plausibly build this as a module column?* A reserved name earns a specific author-time
  diagnosis (`vocab.RESERVED_NAME_REASONS` via `reject_reserved`); everything else gets the generic
  message. (This is why `caller`/`caller_version` were dropped — consumer-side measurement provenance
  with no module-side meaning — while `reference_db`, a join-target-DB hint, was kept.)
- **Additive within a major** (Principles 3/8): new columns are optional; a required field is never
  demoted; anything that changes `artifact.digest` bytes (parquet column set/types) is major-only —
  *except* while a version is still unpublished, where the digest is not yet frozen.
- **Round-trip must stay lossless and idempotent** (Principle 7) — prove it with tests, don't assume.
- **Dogfood a P7/dedup finding before you report it — construct a *real, sensible* example against
  the actual code paths, or it is not a finding.** A round-trip/dedup "loss" that is mechanically
  possible but has no real instantiation is noise; walk the data model with a biologist's eye before
  flagging it. The standing example: `annotations.parquet` dedups on the **variant-effect pair**
  `(variant_key, conclusion, negatives)`. An audit flagged "two rows sharing that key + identical
  `conclusion`/`negatives` but differing `gene`/`phenotype`/`category` collapse to the first — a P7
  loss." It read airtight mechanically, yet it is **non-real**, and trying to build one example proves
  why: sharing a `variant_key` forces a *single locus* (a one-to-many rsid is **expanded to distinct
  coord-keys** by the resolver, so paralogs never share a key) ⟹ one `gene`; and identical
  `conclusion`+`negatives` means the *same effect* ⟹ the same `phenotype`/`category`. `gene` isn't
  even carried in `weights.parquet`, so two such rows are physically indistinguishable regardless of
  keying. The constraint set is empty — no real, sensible module hits it. The **genuine** poly-effect
  loss (one locus, two genotypes, *distinct* conclusions — het "carrier" vs hom "affected") is what
  the variant-effect-pair keying already fixed. Lesson: empirical probing + a real-example test beat a
  plausible-looking mechanistic claim; the mechanistic claim, unfalsified, was a mechanical re-flag of
  an already-closed item.
- **Deterministic ordering is load-bearing** (an implicit consequence of Principle 7, not its own
  charter rule). Parquet bytes depend on **row order**, so `artifact.digest` is order-sensitive:
  **authored row order is preserved** through compile → reverse → recompile and must stay that way.
  Never derive emitted rows, CSV/parquet contents, or manifest fields from `set`/`dict` iteration or
  from polars `mode()`/`unique()` without an explicit stable sort or tie-break (both give *no* order
  guarantee — `mode()` is unstable even call-to-call). Prefer explicit `ORDER BY` in SQL, `sorted(...)`
  /`min(...)` for picks, and first-occurrence (insertion) order for dedup. **Column order and cell
  formatting, by contrast, are normalized, not preserved** (reverse emits a fixed `fieldnames` order;
  values are stripped/canonicalized) — that asymmetry is intended. New orderings get a test.
- `uv run pytest` runs the suite. Use `uv sync` / `uv add`; **never** `uv pip install`.
- New markdown (except this file / `README`) goes in `docs/`.

## Related repos (read-only unless the task targets them)

`just-dna-pipelines` (compiler/discovery, depends on these libs), `just-dna-lite` (app + webui, the
reference consumer), `just-dna-marketplace` (catalog/storage/serving; consumes the `revalidate`/
`needs_upgrade` derivation these libs supply), `just-dna-agents` (MCP surface — its `get_spec_format`/
`list_colors`/`list_icons` are the drift `authoring_reference()`/`RECOMMENDED_*` replace), `just-prs`.
