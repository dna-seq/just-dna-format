"""Result types returned by the compiler. The compiled *manifest* itself is the
`just_dna_format.manifest.ModuleManifest` — these wrap validation/compilation outcomes."""

from pathlib import Path
from typing import Any, Optional

from just_dna_format.manifest import ModuleManifest
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Result of spec validation."""

    valid: bool = Field(description="Whether the spec is valid")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary stats: variant_count, gene_count, genes, categories, study_count",
    )


class CompilationResult(BaseModel):
    """Result of spec compilation, including the emitted manifest."""

    success: bool = Field(description="Whether compilation succeeded")
    output_dir: Optional[Path] = Field(default=None, description="Directory with output parquets")
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    manifest: Optional[ModuleManifest] = Field(
        default=None, description="The manifest written next to the parquets (None on failure)"
    )
