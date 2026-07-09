"""
A machine/LLM-facing authoring reference, **generated from the live models** (RM8).

Consumers (MCP servers, agents, docs) tend to hard-code a prose summary of the DSL — its columns,
vocabularies, genome build — which then **drifts** from the real schema (just-dna-agents' MCP
`get_spec_format` predated the 0.3 columns, for example). `authoring_reference()` derives that summary
by introspecting the Pydantic models and vocabularies, so it is a **single source of truth that cannot
drift**: every consumer renders the current field set. For a full JSON Schema, call
`json_schemas()` (Pydantic's `model_json_schema()` per model).

Dependency-light: this is a top-level aggregator over `spec`/`binning`/`pgx`/`pgs`/`manifest`/`vocab`;
nothing in the package imports it, so it introduces no cycle.
"""

from typing import Any

from pydantic import BaseModel

from just_dna_format.binning import (
    VALID_MEASURE_KINDS,
    ActivityPhenotypeRow,
    CopyNumberRow,
    HeteroplasmyRow,
    MeasureBinRow,
    RepeatAlleleRow,
)
from just_dna_format.manifest import (
    RECOMMENDED_COLORS,
    RECOMMENDED_ICONS,
    SCHEMA_VERSION,
    VALID_ICON_SETS,
    Display,
    GenePanelSpec,
)
from just_dna_format.pgs import (
    VALID_RESEARCH_TIERS,
    VALID_TRAINING_ANCESTRY,
    PgsRow,
)
from just_dna_format.pgx import (
    VALID_FUNCTION_STATUS,
    AlleleFunctionRow,
    DiplotypeRow,
    HaplotypeRow,
)
from just_dna_format.spec import (
    RECOMMENDED_EFFECT_MEASURES,
    RESERVED_FLAGS,
    VALID_CHROMOSOMES,
    VALID_CLIN_SIG,
    VALID_DIRECTIONS,
    VALID_SIGNIFICANCE,
    VALID_STATES,
    Defaults,
    ModuleInfo,
    ModuleSpecConfig,
    StudyRow,
    VariantRow,
)
from just_dna_format.vocab import ACTIONABILITY_SEED, RESERVED_NAMES_0_4

# The authored surface, grouped by role. Order is the reading order for an author/agent.
_MODULE_MODELS: dict[str, type[BaseModel]] = {
    "ModuleSpecConfig": ModuleSpecConfig,
    "ModuleInfo": ModuleInfo,
    "Defaults": Defaults,
    "GenePanelSpec": GenePanelSpec,
    "Display": Display,
}
_VARIANT_MODELS: dict[str, type[BaseModel]] = {
    "VariantRow": VariantRow,
    "StudyRow": StudyRow,
}
_BINNING_MODELS: dict[str, type[BaseModel]] = {
    "MeasureBinRow": MeasureBinRow,
    "ActivityPhenotypeRow": ActivityPhenotypeRow,
    "CopyNumberRow": CopyNumberRow,
    "RepeatAlleleRow": RepeatAlleleRow,
    "HeteroplasmyRow": HeteroplasmyRow,
}
_PGX_MODELS: dict[str, type[BaseModel]] = {
    "HaplotypeRow": HaplotypeRow,
    "AlleleFunctionRow": AlleleFunctionRow,
    "DiplotypeRow": DiplotypeRow,
}
_PGS_MODELS: dict[str, type[BaseModel]] = {"PgsRow": PgsRow}

_ALL_MODELS: dict[str, type[BaseModel]] = {
    **_MODULE_MODELS,
    **_VARIANT_MODELS,
    **_BINNING_MODELS,
    **_PGX_MODELS,
    **_PGS_MODELS,
}


def _type_name(annotation: Any) -> str:
    """A readable type label (`Optional[str]`, `list[str]`, `int`) from a field annotation."""
    return (
        str(annotation)
        .replace("typing.", "")
        .replace("<class '", "")
        .replace("'>", "")
    )


def _describe_model(model: type[BaseModel]) -> list[dict[str, Any]]:
    """Field list for one model, in declaration order — `{name, type, required, description}`."""
    fields = []
    for name, field in model.model_fields.items():
        fields.append(
            {
                "name": name,
                "type": _type_name(field.annotation),
                "required": field.is_required(),
                "description": field.description,
            }
        )
    return fields


def authoring_reference() -> dict[str, Any]:
    """A drift-proof, JSON-serialisable description of the authored DSL — models (field lists),
    vocabularies, reserved names, and the recommended display palette — generated from the live
    schema. Consumers render this instead of a hand-maintained prose summary (RM8)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "genome_build_default": ModuleSpecConfig.model_fields["genome_build"].default,
        "models": {name: _describe_model(model) for name, model in _ALL_MODELS.items()},
        "vocabularies": {
            "state": sorted(VALID_STATES),
            "chromosome": sorted(VALID_CHROMOSOMES),
            "direction": sorted(VALID_DIRECTIONS),
            "stat_significance": sorted(VALID_SIGNIFICANCE),
            "clin_sig": sorted(VALID_CLIN_SIG),
            "measure_kind": sorted(VALID_MEASURE_KINDS),
            "function_status": sorted(VALID_FUNCTION_STATUS),
            "training_ancestry": sorted(VALID_TRAINING_ANCESTRY),
            "research_tier": sorted(VALID_RESEARCH_TIERS),
            "reserved_flags": sorted(RESERVED_FLAGS),
            "icon_set": sorted(VALID_ICON_SETS),
        },
        "open_recommended": {
            "effect_measure": sorted(RECOMMENDED_EFFECT_MEASURES),
            "actionability_seed": sorted(ACTIONABILITY_SEED),
        },
        "reserved_names": sorted(RESERVED_NAMES_0_4),
        "recommended_palette": {"colors": RECOMMENDED_COLORS, "icons": RECOMMENDED_ICONS},
    }


def json_schemas() -> dict[str, Any]:
    """Full JSON Schema per model (Pydantic `model_json_schema()`), for consumers that want the
    machine-validatable form rather than the compact `authoring_reference()` summary."""
    return {name: model.model_json_schema() for name, model in _ALL_MODELS.items()}
