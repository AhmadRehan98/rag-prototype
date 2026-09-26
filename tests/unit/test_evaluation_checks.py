"""The release-gate checks in scripts/run_evaluation.py."""

from src.config.settings import settings
from src.domain.models import ExcludedSource, QueryResponse, Source
from scripts.run_evaluation import check_case, load_cases, summarize


def test_dataset_has_one_case_per_mandatory_family():
    runs = load_cases(settings.resolve_path(settings.EVALUATION_CASES_PATH))
    case_ids = {run["id"] for run in runs}
    assert len(case_ids) == 4
    assert {run["family"] for run in runs} == {
        "policy_authority", "unsupported_sla", "authorization", "malicious_document",
    }
    # Incident 3: the same request from the Engineering and the HR employee.
    authorization = [run for run in runs if run["family"] == "authorization"]
    assert {run["user_id"] for run in authorization} == {"u-eng-104", "u-hr-207"}
    assert len({run["question"] for run in authorization}) == 1


def test_a_case_fails_if_any_of_its_runs_fails():
    results = [
        {"id": "authorization", "family": "authorization", "passed": True},
        {"id": "authorization", "family": "authorization", "passed": False},
        {"id": "unsupported-sla", "family": "unsupported_sla", "passed": True},
    ]
    assert summarize(results) == {
        "authorization": {"passed": 0, "total": 1},
        "unsupported_sla": {"passed": 1, "total": 1},
    }


def source(citation, document_id, version="1.0"):
    return Source(
        citation=citation, chunk_id=citation, document_id=document_id, title="t",
        version=version, status="Current", effective_date=None,
        authority="authoritative", content="c",
    )


def case(question="q?", **expect):
    return {"id": "x", "question": question, "expect": {"status": ["answered"], **expect}}


def test_passing_response_has_no_failures():
    response = QueryResponse(status="answered", answer="- A. [1]", sources=[source(1, "POL")])
    assert check_case(case(cited_documents=["POL"]), response) == []


def test_status_and_citation_failures_are_reported():
    response = QueryResponse(status="insufficient_evidence", answer="- A. [2]",
                             missing_information="A signed schedule.",
                             sources=[source(1, "POL"), source(2, "MEMO")])
    failures = check_case(case(cited_documents=["POL"]), response)
    assert len(failures) == 2


def test_refusal_must_say_what_evidence_is_missing():
    refusal = case(status=["insufficient_evidence"])
    silent = QueryResponse(status="insufficient_evidence", answer="No.")
    explained = QueryResponse(status="insufficient_evidence", answer="No.",
                              missing_information="A signed schedule with response times.")
    assert check_case(refusal, silent) == ["refusal does not say what evidence is missing"]
    assert check_case(refusal, explained) == []


def test_forbidden_source_matches_id_or_id_at_version():
    response = QueryResponse(status="answered", answer="- A. [1]",
                             sources=[source(1, "POL", version="2.1")])
    assert check_case(case(forbidden_sources=["POL@2.1"]), response)
    assert check_case(case(forbidden_sources=["POL"]), response)
    assert not check_case(case(forbidden_sources=["POL@3.0"]), response)


def test_excluded_source_must_be_reported():
    response = QueryResponse(status="answered", answer="- A. [1]", sources=[source(1, "POL")],
                             excluded_sources=[ExcludedSource(document_id="POL", title="t",
                                                              version="2.1", status="Retired",
                                                              reason="retired")])
    assert not check_case(case(excluded_sources=["POL@2.1"]), response)
    assert check_case(case(excluded_sources=["KB"]), response)


def test_restricted_text_anywhere_in_the_response_fails():
    response = QueryResponse(status="answered", answer="- Leave is handled by HR. [1]",
                             missing_information="See APX-HR-CASE-778.", sources=[source(1, "POL")])
    assert check_case(case(forbidden_text_sets=["restricted_hr_case"]), response)


def test_terms_echoed_from_the_question_are_not_leaks():
    response = QueryResponse(status="answered", answer="- Nothing about APX-HR-CASE-778 is available. [1]",
                             sources=[source(1, "POL")])
    checked = case(question="What is the status of APX-HR-CASE-778?",
                   forbidden_text_sets=["restricted_hr_case"])
    assert check_case(checked, response) == []
