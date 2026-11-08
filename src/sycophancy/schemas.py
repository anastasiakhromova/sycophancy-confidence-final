"""Typed records and serializable diagnostics shared by the preparation pipeline."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .constants import PROMPT_TEMPLATE_VERSION


class Domain(str, Enum):
    """The five preregistered dataset domains."""

    GEOGRAPHY = "geography"
    SCIENCE = "science"
    HISTORY = "history"
    TECHNOLOGY = "technology"
    GENERAL_KNOWLEDGE = "general_knowledge"


class ConfidenceLevel(str, Enum):
    """Ordered within-claim experimental conditions."""

    LOW = "low"
    NEUTRAL = "neutral"
    HIGH = "high"


@dataclass(frozen=True)
class Claim:
    """A candidate false claim; verification is a curator's explicit assertion.

    Construct through ``validate_claims`` at the input boundary. Dataclass type
    annotations alone do not validate arbitrary Python values.
    """

    claim_id: str
    domain: Domain
    false_claim: str
    false_answer: str
    true_answer: str
    source: str | None = None
    source_type: str | None = None
    verified: bool = False
    notes: str | None = None


@dataclass(frozen=True)
class ExperimentItem:
    """One rendered condition with its unchanged claim metadata."""

    experiment_item_id: str
    claim_id: str
    domain: Domain
    confidence: ConfidenceLevel
    false_claim: str
    false_answer: str
    true_answer: str
    prompt: str
    verified: bool


@dataclass
class ValidationReport:
    """Deterministic diagnostics; counts never certify factual correctness."""

    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: int = 0
    claims_per_domain: dict[str, int] = field(
        default_factory=lambda: {domain.value: 0 for domain in Domain}
    )
    duplicate_count: int = 0
    missing_values: dict[str, int] = field(default_factory=dict)
    prompt_count: int = 0
    prompts_per_confidence: dict[str, int] = field(
        default_factory=lambda: {level.value: 0 for level in ConfidenceLevel}
    )
    average_prompt_length: dict[str, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Whether no structural errors have been recorded."""
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-ready data without run-dependent timestamps."""
        return {
            **asdict(self),
            "validation_status": "PASSED" if self.passed else "FAILED",
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        }


class DatasetValidationError(ValueError):
    """A failed validation with all diagnostics attached in ``report``."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__("\n".join(report.errors) or "Dataset validation failed.")
