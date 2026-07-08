# just-dna-format — Constitution

The durable design charter for `just-dna-format` and `just-dna-compiler`: what these packages are
for, what they will never do, and the invariants every release upholds.

Unlike [`ROADMAP.md`](ROADMAP.md) (plans, revised often) and
[`CHANGELOG.md`](CHANGELOG.md) (what shipped), **this document changes only by deliberate
amendment** — so the core commitments below cannot be lost or altered as a side effect of routine
roadmap edits. When a roadmap plan conflicts with this document, this document wins. When a plan
graduates into a durable rule, promote it here on purpose.

## Goals

- Be the **declarative schema contract** for just-dna annotation modules and the **reference
  compiler** that targets it: an authored spec (`module_spec.yaml` + CSVs) → a `manifest.json` plus a
  three-parquet artifact, carrying per-input and per-artifact hashes and a Merkle `artifact.digest`.
- Stay **dependency-light, in tiers.** `just-dna-format` (schema + integrity) costs only `pydantic`,
  so any verify-only client can depend on it; `just-dna-compiler` adds polars/duckdb/pyyaml for the
  transform. Consumers pick the tier they need and pull nothing heavier.
- Make **integrity the identity.** A version is defined by its content digest, byte-reproducible by
  anyone who holds the inputs.

## Non-goals

- **No heavyweight dependencies in these libs.** Never pull Dagster, LLM SDKs, or HuggingFace.
  Orchestration and AI-assisted authoring live in `just-dna-pipelines`; artifact storage and serving
  live in `just-dna-marketplace`.
- **No network.** These packages never download reference data. The Ensembl resolver is
  **inject-only**; provisioning is the caller's job (app-side).
- **Not a runtime.** The format is data, not a program (Principle 1). A consumer must be able to read
  a module without executing anything the module ships.
- **No UI and no gene–disease inference.** The format catalogs curated annotations that consumers
  *join* against variant data; interpretation and presentation belong to those consumers.

## Principles (invariants)

1. **Declarative, never code.** A module is data — CSV rows, YAML, and lookup tables — never a
   program. Expressive power comes from tables (e.g. diplotype/haplotype lookups), not from a
   scripting language. Turing-complete code in cells (Lua, Python, side-effecting expressions) is
   **rejected**: it breaks server-side-compile safety (arbitrary code execution in the trusted
   compile path), destroys byte-reproducibility (hashing inputs is meaningless if behaviour is code),
   and forces every consumer to embed a runtime. **Declarative *grammars* are welcome, though** — a
   pattern language is data, not a program. If tables are ever outgrown, the sanctioned escapes are
   (a) a **non-Turing-complete boolean predicate** over genotypes (e.g. `rs429358==C AND rs7412==C`)
   and (b) **declarative pattern grammars** such as **regular expressions** for matching allele
   strings / genotypes (e.g. a regex over a PGx star-string), evaluated by a small sandboxable engine
   — a linear-time/safe one, so there is no catastrophic-backtracking (ReDoS) exposure. The line is
   **Turing-completeness and side effects, not apparent sophistication**: bounded predicates and
   pattern grammars are in; general code is out. None of these are needed yet — they are escape
   hatches, available if a task genuinely demands, never a default.

2. **No network; inject-only.** The libraries do not fetch. Any reference (Ensembl, ClinVar) is
   injected by the caller; with nothing injected, the compiler skips resolution with a warning rather
   than downloading.

3. **Backward-compatible within a major version.** Inside an `N.x` line every change is additive and
   non-breaking: `schema_version` is unchanged, existing modules keep validating, and anything
   superseded is kept as a **working derived alias**. **Breaking changes land only at a major bump.**
   The default retirement is two-step — *deprecate at the major* (still readable, emits a deprecation
   event), *remove at the next major*. Purely-internal dead weight may be removed outright at a major.
   Anything that changes `artifact.digest` bytes (parquet column set or types) is inherently
   major-only, because the digest is a version's immutable identity. The running list of items queued
   for the next major lives in [`ROADMAP.md`](ROADMAP.md) ("1.0 cleanup candidates").

4. **Integrity and immutability.** All hashes are SHA-256, lowercase hex, prefixed `sha256:`.
   `artifact.digest` (a Merkle root over the artifact files) is the version's content identity. A
   published version's bytes are **never mutated**; withdrawal is a *yank* (drop from listings, keep
   fetchable), not an edit. Parquet is not byte-deterministic across polars/arrow versions, so
   reproducibility is pinned via `compiler_version` and the resolved reference.

5. **Orthogonal axes, no overloaded fields.** Each concept gets its own column or table; a field must
   not pile up independent axes. (The legacy `state` field — conflating statistical significance,
   effect direction, and a genotype descriptor — is the anti-pattern being unwound in 0.3.) Because
   Principle 3 makes names and vocabularies permanent within a major, **audit every new name against
   likely future additions before adding it**; the reserved namespace is tracked in
   [`ROADMAP.md`](ROADMAP.md).

6. **Vocabulary idiom.** Constrained vocabularies are `frozenset[str]` + a validator, not
   `Enum`/`Literal`. This keeps a vocabulary additive and inspectable, and matches the existing schema.

7. **Round-trip fidelity and idempotency.** The format is declarative data, so the reference
   transform must behave like one. Within a major version:
   - **Lossless round-trip.** `compile_module` → `reverse_module` → `compile_module` preserves every
     authored value. Reversing a compiled artifact back to the spec DSL and recompiling must not drop
     or mutate a column (this is why phase is carried in the artifact, not discarded — a phased `A|G`
     survives the round-trip). If a value cannot survive the round-trip, the artifact is missing a
     field, not the spec.
   - **Idempotency.** Compiling the same spec twice in a fixed compiler environment yields the same
     `artifact.digest`; and every derivation/upgrade is a fixed point — `row.upgraded().upgraded()
     == row.upgraded()`, and the read-time `effective_*` aliases return a set column unchanged. A
     derivation must never oscillate or accumulate.

   These are enforced by tests, not merely asserted here. (Cross-*version* byte-reproducibility is
   still bounded by Principle 4: parquet is not deterministic across polars/arrow versions, so the
   digest guarantee is *within* a fixed `compiler_version`.)

8. **Requiredness is monotonic within a major (field-optionality compatibility).** Whether a field is
   required is itself part of the contract and may only tighten, never loosen, inside an `N.x` line:
   - A field that **any earlier version in the line made required stays required** — it is never
     demoted to optional. Demoting it would let a newer module omit data an older consumer depends
     on. (This is why 0.3 keeps `state` and the ClinVar booleans **required/authoritative** and adds
     `direction`/`clin_sig` as *optional* orthogonal axes with derived fallbacks, rather than the
     inverse the roadmap first sketched.)
   - A **new** field may be introduced and even treated as required for freshly-authored specs, **but
     only if existing data still validates** — i.e. it is optional/defaulted with respect to every
     already-published module (which never set it), so nothing previously valid becomes invalid.
   - The forbidden moves — demoting an existing required field to optional, promoting an existing
     optional field to unconditionally-required, or retyping a field — are **breaking changes
     reserved for the next major** (the requiredness rehaul), tracked in
     [`ROADMAP.md`](ROADMAP.md)'s 1.0-cleanup list. Until then, all of the above holds.

   In short: optionality tightens forward-only and never invalidates older data; loosening waits for
   the major bump. This complements Principle 3 (additive within a major) by pinning the *requiredness*
   axis specifically, because it was the axis most easily missed.

## Amendments

This document is amended deliberately, never incidentally. `ROADMAP.md` holds plans and the
`1.0` cleanup tracker; `CHANGELOG.md` records what shipped; coding-style conventions (type
hints, pathlib, absolute imports) live with the code. If any of those conflict with a principle here,
this document governs — resolve the conflict by amending one or the other on purpose, not by letting
the two drift.
