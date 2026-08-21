from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


ONTOLOGY_VERSION = "career-v1"


class EntityType(str, Enum):
    PERSON = "PERSON"
    EXPERIENCE = "EXPERIENCE"
    ORGANIZATION = "ORGANIZATION"
    ROLE = "ROLE"
    SKILL = "SKILL"
    EDUCATION = "EDUCATION"
    CERTIFICATION = "CERTIFICATION"
    PROJECT = "PROJECT"
    ACHIEVEMENT = "ACHIEVEMENT"
    LANGUAGE = "LANGUAGE"
    LICENSE = "LICENSE"
    PORTFOLIO_ITEM = "PORTFOLIO_ITEM"


class Cardinality(str, Enum):
    ONE = "ONE"
    MANY = "MANY"


class PrivacyClass(str, Enum):
    PUBLIC_SAFE = "PUBLIC_SAFE"
    CAREER_PRIVATE = "CAREER_PRIVATE"
    PERSONAL_SENSITIVE = "PERSONAL_SENSITIVE"
    HIGHLY_SENSITIVE = "HIGHLY_SENSITIVE"
    SECRET_FORBIDDEN = "SECRET_FORBIDDEN"


class DisclosureScope(str, Enum):
    INTERNAL_ONLY = "INTERNAL_ONLY"
    MATCHING_ONLY = "MATCHING_ONLY"
    APPLICATION_ALLOWED = "APPLICATION_ALLOWED"
    PUBLIC_EXPORT_ALLOWED = "PUBLIC_EXPORT_ALLOWED"


class Predicate(str, Enum):
    PERSON_DISPLAY_NAME = "PERSON.DISPLAY_NAME"

    ROLE_NAME = "ROLE.NAME"

    EXPERIENCE_ROLE = "EXPERIENCE.ROLE"
    EXPERIENCE_DURATION_MONTHS = "EXPERIENCE.DURATION_MONTHS"
    EXPERIENCE_ORGANIZATION = "EXPERIENCE.ORGANIZATION"
    EXPERIENCE_START_DATE = "EXPERIENCE.START_DATE"
    EXPERIENCE_END_DATE = "EXPERIENCE.END_DATE"
    EXPERIENCE_LOCATION = "EXPERIENCE.LOCATION"
    EXPERIENCE_EMPLOYMENT_TYPE = "EXPERIENCE.EMPLOYMENT_TYPE"
    EXPERIENCE_RESPONSIBILITY = "EXPERIENCE.RESPONSIBILITY"
    EXPERIENCE_SKILL_USED = "EXPERIENCE.SKILL_USED"
    EXPERIENCE_ACHIEVEMENT = "EXPERIENCE.ACHIEVEMENT"

    SKILL_NAME = "SKILL.NAME"
    SKILL_PROFICIENCY = "SKILL.PROFICIENCY"
    SKILL_LAST_USED = "SKILL.LAST_USED"
    SKILL_CONTEXT = "SKILL.CONTEXT"

    EDUCATION_INSTITUTION = "EDUCATION.INSTITUTION"
    EDUCATION_PROGRAM = "EDUCATION.PROGRAM"
    EDUCATION_FIELD = "EDUCATION.FIELD"
    EDUCATION_START_DATE = "EDUCATION.START_DATE"
    EDUCATION_END_DATE = "EDUCATION.END_DATE"
    EDUCATION_COMPLETION_STATE = "EDUCATION.COMPLETION_STATE"

    CERTIFICATION_NAME = "CERTIFICATION.NAME"
    CERTIFICATION_ISSUER = "CERTIFICATION.ISSUER"
    CERTIFICATION_ISSUED_AT = "CERTIFICATION.ISSUED_AT"
    CERTIFICATION_EXPIRES_AT = "CERTIFICATION.EXPIRES_AT"
    CERTIFICATION_CREDENTIAL_REFERENCE = "CERTIFICATION.CREDENTIAL_REFERENCE"

    PROJECT_NAME = "PROJECT.NAME"
    PROJECT_ROLE = "PROJECT.ROLE"
    PROJECT_DESCRIPTION = "PROJECT.DESCRIPTION"
    PROJECT_SKILL_USED = "PROJECT.SKILL_USED"
    PROJECT_OUTCOME = "PROJECT.OUTCOME"
    PROJECT_URL = "PROJECT.URL"

    LANGUAGE_LANGUAGE = "LANGUAGE.LANGUAGE"
    LANGUAGE_PROFICIENCY = "LANGUAGE.PROFICIENCY"


@dataclass(frozen=True)
class PredicateSpec:
    subject_type: EntityType
    value_type: str
    cardinality: Cardinality
    privacy_class: PrivacyClass
    disclosure_default: DisclosureScope
    minimum_identity: bool = False
    ontology_version: str = ONTOLOGY_VERSION


def _spec(
    subject_type: EntityType,
    value_type: str,
    cardinality: Cardinality,
    *,
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC_SAFE,
    disclosure_default: DisclosureScope = DisclosureScope.PUBLIC_EXPORT_ALLOWED,
    minimum_identity: bool = False,
) -> PredicateSpec:
    return PredicateSpec(
        subject_type=subject_type,
        value_type=value_type,
        cardinality=cardinality,
        privacy_class=privacy_class,
        disclosure_default=disclosure_default,
        minimum_identity=minimum_identity,
    )


_PREDICATES: dict[Predicate, PredicateSpec] = {
    Predicate.PERSON_DISPLAY_NAME: _spec(
        EntityType.PERSON,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),

    Predicate.ROLE_NAME: _spec(
        EntityType.ROLE,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),

    Predicate.EXPERIENCE_ROLE: _spec(
        EntityType.EXPERIENCE,
        "ROLE_REF",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.EXPERIENCE_DURATION_MONTHS: _spec(
        EntityType.EXPERIENCE,
        "INTEGER",
        Cardinality.ONE,
    ),
    Predicate.EXPERIENCE_ORGANIZATION: _spec(
        EntityType.EXPERIENCE,
        "ORGANIZATION_REF",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.EXPERIENCE_START_DATE: _spec(
        EntityType.EXPERIENCE, "DATE", Cardinality.ONE
    ),
    Predicate.EXPERIENCE_END_DATE: _spec(
        EntityType.EXPERIENCE, "DATE", Cardinality.ONE
    ),
    Predicate.EXPERIENCE_LOCATION: _spec(
        EntityType.EXPERIENCE, "TEXT", Cardinality.ONE
    ),
    Predicate.EXPERIENCE_EMPLOYMENT_TYPE: _spec(
        EntityType.EXPERIENCE, "TEXT", Cardinality.ONE
    ),
    Predicate.EXPERIENCE_RESPONSIBILITY: _spec(
        EntityType.EXPERIENCE, "TEXT", Cardinality.MANY
    ),
    Predicate.EXPERIENCE_SKILL_USED: _spec(
        EntityType.EXPERIENCE, "SKILL_REF", Cardinality.MANY
    ),
    Predicate.EXPERIENCE_ACHIEVEMENT: _spec(
        EntityType.EXPERIENCE, "ACHIEVEMENT_REF", Cardinality.MANY
    ),

    Predicate.SKILL_NAME: _spec(
        EntityType.SKILL,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.SKILL_PROFICIENCY: _spec(
        EntityType.SKILL, "TEXT", Cardinality.ONE
    ),
    Predicate.SKILL_LAST_USED: _spec(
        EntityType.SKILL, "DATE", Cardinality.ONE
    ),
    Predicate.SKILL_CONTEXT: _spec(
        EntityType.SKILL, "TEXT", Cardinality.MANY
    ),

    Predicate.EDUCATION_INSTITUTION: _spec(
        EntityType.EDUCATION, "TEXT", Cardinality.ONE
    ),
    Predicate.EDUCATION_PROGRAM: _spec(
        EntityType.EDUCATION, "TEXT", Cardinality.ONE
    ),
    Predicate.EDUCATION_FIELD: _spec(
        EntityType.EDUCATION, "TEXT", Cardinality.ONE
    ),
    Predicate.EDUCATION_START_DATE: _spec(
        EntityType.EDUCATION, "DATE", Cardinality.ONE
    ),
    Predicate.EDUCATION_END_DATE: _spec(
        EntityType.EDUCATION, "DATE", Cardinality.ONE
    ),
    Predicate.EDUCATION_COMPLETION_STATE: _spec(
        EntityType.EDUCATION, "TEXT", Cardinality.ONE
    ),

    Predicate.CERTIFICATION_NAME: _spec(
        EntityType.CERTIFICATION,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.CERTIFICATION_ISSUER: _spec(
        EntityType.CERTIFICATION,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.CERTIFICATION_ISSUED_AT: _spec(
        EntityType.CERTIFICATION, "DATE", Cardinality.ONE
    ),
    Predicate.CERTIFICATION_EXPIRES_AT: _spec(
        EntityType.CERTIFICATION, "DATE", Cardinality.ONE
    ),
    Predicate.CERTIFICATION_CREDENTIAL_REFERENCE: _spec(
        EntityType.CERTIFICATION,
        "VAULT_OR_SAFE_REFERENCE",
        Cardinality.ONE,
        privacy_class=PrivacyClass.PERSONAL_SENSITIVE,
        disclosure_default=DisclosureScope.APPLICATION_ALLOWED,
    ),

    Predicate.PROJECT_NAME: _spec(
        EntityType.PROJECT,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.PROJECT_ROLE: _spec(
        EntityType.PROJECT, "TEXT", Cardinality.ONE
    ),
    Predicate.PROJECT_DESCRIPTION: _spec(
        EntityType.PROJECT, "TEXT", Cardinality.ONE
    ),
    Predicate.PROJECT_SKILL_USED: _spec(
        EntityType.PROJECT, "SKILL_REF", Cardinality.MANY
    ),
    Predicate.PROJECT_OUTCOME: _spec(
        EntityType.PROJECT, "TEXT", Cardinality.MANY
    ),
    Predicate.PROJECT_URL: _spec(
        EntityType.PROJECT, "URL", Cardinality.MANY
    ),

    Predicate.LANGUAGE_LANGUAGE: _spec(
        EntityType.LANGUAGE,
        "TEXT",
        Cardinality.ONE,
        minimum_identity=True,
    ),
    Predicate.LANGUAGE_PROFICIENCY: _spec(
        EntityType.LANGUAGE, "TEXT", Cardinality.ONE
    ),
}


def predicate_spec(predicate: Predicate) -> PredicateSpec:
    return _PREDICATES[predicate]
