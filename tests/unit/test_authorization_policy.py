"""AuthorizationPolicy: supplied entitlements, AND semantics, default_rule."""

import json
from types import SimpleNamespace as NS

import pytest

from src.authorization.policy import AuthorizationPolicy
from src.config.settings import settings


def user(*groups: str):
    return NS(user_id="u-test", groups=[NS(group=g) for g in groups])


def document(classification: str, allow=(), deny=(), document_id: str = "DOC-1"):
    groups = [NS(group=g, allowed=True) for g in allow]
    groups += [NS(group=g, allowed=False) for g in deny]
    return NS(
        document_id=document_id,
        classification=classification,
        override=NS(groups=groups) if groups else None,
    )


def load_json(path):
    return json.loads(settings.resolve_path(path).read_text(encoding="utf-8"))


def test_supplied_data_only_hr_investigations_can_read_the_hr_case():
    """Builds each document the way seed_data stores it (corpus allowed_groups
    plus entitlements document_overrides) and checks every user/document pair."""
    policy = AuthorizationPolicy()
    entitlements = load_json(settings.ENTITLEMENTS_JSON_PATH)
    overrides = {o["document_id"]: o for o in entitlements["document_overrides"]}
    users = load_json(settings.IDENTITIES_JSON_PATH)["users"]
    corpus = [
        json.loads(line)
        for line in settings.resolve_path(settings.CORPUS_JSONL_PATH).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    for record in corpus:
        override = overrides.get(record["document_id"], {})
        doc = document(
            record["classification"],
            allow=set(record["allowed_groups"]) | set(override.get("allow_groups", [])),
            deny=override.get("deny_groups", []),
            document_id=record["document_id"],
        )
        for identity in users:
            allowed = policy.evaluate_access(user(*identity["groups"]), doc).is_allowed
            expected = record["document_id"] != "APX-HR-CASE-778" or identity["user_id"] == "u-hr-207"
            assert allowed == expected, (identity["user_id"], record["document_id"])


RULES = [
    {"classification": "INTERNAL", "allow_groups": ["all_employees"]},
    {"classification": "RESTRICTED", "allow_groups": ["hr"]},
]


def test_deny_override_wins_over_matching_allows():
    policy = AuthorizationPolicy(rules=RULES)
    doc = document("INTERNAL", allow=["all_employees"], deny=["engineering"])
    assert not policy.evaluate_access(user("all_employees", "engineering"), doc).is_allowed


def test_allow_override_cannot_widen_a_classification_rule():
    policy = AuthorizationPolicy(rules=RULES)
    doc = document("RESTRICTED", allow=["all_employees"])
    assert not policy.evaluate_access(user("all_employees"), doc).is_allowed


def test_allow_list_narrows_access():
    policy = AuthorizationPolicy(rules=RULES)
    doc = document("INTERNAL", allow=["finance"])
    assert not policy.evaluate_access(user("all_employees"), doc).is_allowed
    assert policy.evaluate_access(user("all_employees", "finance"), doc).is_allowed


@pytest.mark.parametrize("default_rule, expected", [("deny", False), ("allow", True)])
def test_default_rule_only_applies_to_classifications_without_a_rule(default_rule, expected):
    policy = AuthorizationPolicy(rules=RULES, default_rule=default_rule)
    assert policy.evaluate_access(user("all_employees"), document("UNKNOWN")).is_allowed is expected
    # A classification that has a rule is unaffected by the default.
    assert not policy.evaluate_access(user("all_employees"), document("RESTRICTED")).is_allowed


def test_default_allow_still_honours_deny_overrides():
    policy = AuthorizationPolicy(rules=RULES, default_rule="allow")
    doc = document("UNKNOWN", deny=["engineering"])
    assert not policy.evaluate_access(user("engineering"), doc).is_allowed


def test_invalid_default_rule_is_rejected():
    with pytest.raises(ValueError):
        AuthorizationPolicy(rules=RULES, default_rule="Allow")


def test_missing_entitlements_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        AuthorizationPolicy(entitlements_path=tmp_path / "missing.json")


def test_verdict_does_not_reveal_the_document_id():
    policy = AuthorizationPolicy(rules=RULES)
    doc = document("RESTRICTED", deny=["engineering"], document_id="SECRET-CASE-1")
    result = policy.evaluate_access(user("engineering"), doc)
    assert not result.is_allowed
    assert "SECRET-CASE-1" not in repr(result)
