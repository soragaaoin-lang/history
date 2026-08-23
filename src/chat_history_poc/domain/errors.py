class PocError(Exception):
    """Base error with a stable machine-readable code."""

    code = "POC_ERROR"

    def __str__(self) -> str:
        return f"{self.code}: {super().__str__()}"


class SessionNotFoundError(PocError):
    code = "SESSION_NOT_FOUND"


class DecisionValidationError(PocError):
    code = "DECISION_VALIDATION_ERROR"


class EvidenceNotFoundError(PocError):
    code = "DECISION_EVIDENCE_NOT_FOUND"


class ProjectionInputError(PocError):
    code = "PROJECTION_INPUT_ERROR"


class SectionBundleError(PocError):
    code = "SECTION_BUNDLE_ERROR"


class IntegrationCandidateError(PocError):
    code = "INTEGRATION_CANDIDATE_ERROR"


class IntegrationAdjudicationError(PocError):
    code = "INTEGRATION_ADJUDICATION_ERROR"


class LifecycleAdjudicationError(PocError):
    code = "LIFECYCLE_ADJUDICATION_ERROR"


class SignalAnnotationError(PocError):
    code = "SIGNAL_ANNOTATION_ERROR"


class KnowledgeExperimentError(PocError):
    code = "KNOWLEDGE_EXPERIMENT_ERROR"
