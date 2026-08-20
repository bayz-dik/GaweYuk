def test_official_current_evidence_wins_salary_but_conflict_is_retained():
    from onejob.ingestion.consensus import resolve_field_consensus
    evidence = [
        {
            "evidence_id": "ats",
            "value": [6500000, 8000000],
            "confidence": 0.98,
            "evidence_family_id": "ats",
        },
        {
            "evidence_id": "portal",
            "value": [5000000, 7000000],
            "confidence": 0.78,
            "evidence_family_id": "portal",
        },
    ]

    result = resolve_field_consensus("salary", evidence)

    assert result.selected_value == [6500000, 8000000]
    assert result.conflicting_evidence_ids == ["portal"]
    assert result.confidence >= 0.90


def test_identity_is_deterministic_for_equivalent_company_job():
    from onejob.ingestion.identity import company_id_for, job_identity_key

    company_a = company_id_for("PT Example Manufacturing")
    company_b = company_id_for("  PT Example Manufacturing  ")

    assert company_a == company_b
    assert company_a.startswith("cmp-")

    job_a = job_identity_key(
        company_a,
        "production operator",
        "bekasi",
    )
    job_b = job_identity_key(
        company_b,
        "production operator",
        "bekasi",
    )

    assert job_a == job_b
    assert job_a.startswith("job-")


def test_matching_external_requisition_identity_scores_one():
    from onejob.ingestion.identity import identity_score

    left = {
        "source_key": "greenhouse",
        "external_id": "req-123",
        "company": "example",
        "title": "production operator",
        "location": "bekasi",
        "description": "operate machines",
    }

    right = {
        "source_key": "greenhouse",
        "external_id": "req-123",
        "company": "example",
        "title": "operator produksi",
        "location": "bekasi",
        "description": "different wording",
    }

    assert identity_score(left, right) == 1.0


def test_source_conflict_retains_conflicting_evidence():
    from onejob.ingestion.consensus import SourceConflict

    conflict = SourceConflict(
        conflict_id="conf-1",
        canonical_job_id="job-1",
        field_name="salary",
        status="OPEN",
        evidence_ids=["ats", "portal"],
    )

    assert conflict.field_name == "salary"
    assert conflict.evidence_ids == ["ats", "portal"]
