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
    info: list[str] = Field(
        default_factory=list,
        description=(
            "Informational notes — neither errors nor warnings (nothing is wrong). Used to surface "
            "accepted-but-noteworthy input, e.g. non-reserved `flags` tags (the flags vocabulary is "
            "open, so an unknown tag is INFO, not a warning). See ROADMAP 0.3 item 4."
        ),
    )
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Summary stats (populated only when the spec has variants). De-facto contract keys: "
            "`variant_count` (distinct variant keys), `unique_rsids`, `gene_count`, `genes` (sorted, "
            "None filtered), `categories` (sorted, None filtered), `study_count`, `clinvar_count`, "
            "`pathogenic_count`, `benign_count`, and `module_name` (when the yaml loaded)."
        ),
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
