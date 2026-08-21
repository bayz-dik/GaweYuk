from __future__ import annotations


class CareerTwinError(RuntimeError):
    """Base class for Career Twin Slice 2 domain errors."""


class SuggestionNotFound(CareerTwinError):
    pass


class CandidateNotFound(CareerTwinError):
    pass


class ConflictNotFound(CareerTwinError):
    pass


class StaleSuggestionState(CareerTwinError):
    pass


class StaleClaimState(CareerTwinError):
    pass


class StaleConflictState(CareerTwinError):
    pass


class InvalidEntityResolution(CareerTwinError):
    pass


class InvalidSuggestionTransition(CareerTwinError):
    pass


class InvalidConflictResolution(CareerTwinError):
    pass


class SuppressedSuggestion(CareerTwinError):
    pass


class DuplicateSuggestion(CareerTwinError):
    pass


class OntologyViolation(CareerTwinError):
    pass


class IdempotencyConflict(CareerTwinError):
    pass


class AuthorizationDenied(CareerTwinError):
    pass


class PrivacyBoundaryViolation(CareerTwinError):
    pass
