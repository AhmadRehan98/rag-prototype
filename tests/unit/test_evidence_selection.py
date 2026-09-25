"""EvidenceSelector: relevance gate, status-based trust, supersession, order."""

from src.evidence.selection import EvidenceSelector

selector = EvidenceSelector(min_similarity=0.6)


def ids(items):
    return [(item.chunk.document_id, item.chunk.version) for item in items]


def reasons(evidence_set):
    return {(item.chunk.document_id, item.chunk.version): item.reason for item in evidence_set.excluded}


def test_irrelevant_chunks_are_dropped_silently(make_chunk):
    result = selector.select([make_chunk("A", similarity=0.59), make_chunk("B", similarity=None)])
    assert result.evidence == [] and result.excluded == []
    assert not result.is_sufficient


def test_retired_unverified_and_unknown_statuses_are_excluded(make_chunk):
    result = selector.select([
        make_chunk("RET", status="Retired"),
        make_chunk("UNV", status="Unverified"),
        make_chunk("ODD", status="Draft"),
        make_chunk("CUR", status="Current"),
    ])
    assert ids(result.evidence) == [("CUR", "1.0")]
    assert reasons(result) == {
        ("RET", "1.0"): "retired",
        ("UNV", "1.0"): "unverified",
        ("ODD", "1.0"): "unrecognized_status",
    }


def test_retired_version_is_never_evidence_even_when_more_similar(make_chunk):
    result = selector.select([
        make_chunk("POL", version="2.1", status="Retired", effective_date="2024-03-15", similarity=0.9),
        make_chunk("POL", version="3.0", status="Current", effective_date="2026-07-01", similarity=0.7),
    ])
    assert ids(result.evidence) == [("POL", "3.0")]
    assert reasons(result) == {("POL", "2.1"): "retired"}


def test_older_trusted_version_is_superseded(make_chunk):
    result = selector.select([
        make_chunk("POL", version="1.9", effective_date="2025-01-01", similarity=0.9),
        make_chunk("POL", version="1.10", effective_date="2025-01-01", similarity=0.7),
    ])
    # Same date: numeric version comparison, so 1.10 > 1.9.
    assert ids(result.evidence) == [("POL", "1.10")]
    assert reasons(result) == {("POL", "1.9"): "superseded"}


def test_advisory_is_labelled_and_ordered_after_authoritative(make_chunk):
    result = selector.select([
        make_chunk("MEMO", status="Active advisory", similarity=0.9),
        make_chunk("MATRIX", status="Current", similarity=0.65),
        make_chunk("POLICY", status="Current", similarity=0.8),
    ])
    assert ids(result.evidence) == [("POLICY", "1.0"), ("MATRIX", "1.0"), ("MEMO", "1.0")]
    assert [item.authority for item in result.evidence] == ["authoritative", "authoritative", "advisory"]


def test_status_matching_ignores_case_and_whitespace(make_chunk):
    result = selector.select([make_chunk("A", status="  CURRENT ")])
    assert ids(result.evidence) == [("A", "1.0")]
