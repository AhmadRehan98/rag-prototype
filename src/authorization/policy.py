"""
Access requires passing ALL of:
1. Explicit document-level overrides (deny, then allow-list).
2. Classification-level entitlement rules.
3. The entitlements default_rule for classifications with no rule (deny if unset).
"""

import logging
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
from src.config.settings import settings
from src.database.models import DocumentModel, UserModel


@dataclass(frozen=True)
class AuthorizationResult:
    """Immutable authorization verdict"""

    is_allowed: bool
    reason: str
    matched_rule: str | None = None
    document_id: str | None = None
    user_id: str | None = None


class AuthorizationPolicy:
    """Application-level document authorization policy.

    Rules in order checked. You have to pass the first three without automatic denial to get access.

    1. Check for an explicit document-level deny override

    2. Check for an explicit document-level allow override. If an allow groups exist, the user must belong to one of them. Passing this check does not grant access by itself.

    3. Classification-level entitlement: The document's classification must be permitted for one of the user's groups. This is always required.

    4. Default rule: A classification with no rule gets the entitlements file's default_rule. Overrides from steps 1 and 2 still apply.
    """

    def __init__(
        self,
        entitlements_path: Path | str | None = None,
        rules: list[dict[str, Any]] | None = None,
        default_rule: str = "deny",
    ) -> None:
        self.classification_rules: dict[str, dict[str, Any]] = {}
        self.default_rule = "deny"

        if rules is not None:
            self._init_rules(rules)
            self._set_default_rule(default_rule)
        else:
            resolved_path = (
                Path(entitlements_path)
                if entitlements_path is not None
                else settings.resolve_path(settings.ENTITLEMENTS_JSON_PATH)
            )
            self._load_from_file(resolved_path)

    def _init_rules(
        self,
        rules: list[dict[str, Any]],
    ) -> None:
        for rule in rules:
            classification = rule.get("classification")

            if not classification:
                continue

            self.classification_rules[classification] = {
                "rule_id": rule.get(
                    "rule_id",
                    "classification_rule",
                ),
                "allow_groups": set(rule.get("allow_groups", [])),
            }

    def _load_from_file(
        self,
        path: Path,
    ) -> None:
        if not path.exists():
            logger.warning("Entitlements json file can't be found at path %s", path)
            return

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        self._init_rules(data.get("rules", []))
        # A missing default_rule is treated as deny
        self._set_default_rule(data.get("default_rule", "deny"))

    def _set_default_rule(
        self,
        default_rule: str,
    ) -> None:
        # Reject anything unexpected
        if default_rule not in ("allow", "deny"):
            raise ValueError(
                f"Invalid default_rule {default_rule!r}; expected 'allow' or 'deny'."
            )
        self.default_rule = default_rule

    def evaluate_access(
        self,
        user: UserModel,
        document: DocumentModel,
    ) -> AuthorizationResult:

        user_groups = {group.group for group in user.groups}

        # 1&2. Explicit document-level overrides
        if document.override is not None:
            denied_groups = {
                group.group for group in document.override.groups if not group.allowed
            }

            allowed_groups = {
                group.group for group in document.override.groups if group.allowed
            }

            # Explicit deny always wins.
            matching_denies = user_groups & denied_groups
            if matching_denies:
                return AuthorizationResult(
                    is_allowed=False,
                    reason=(
                        f"Access denied by explicit override on "
                        f"{document.document_id}: user is in a "
                        f"denied group."
                    ),
                    matched_rule="document_override_deny",
                    document_id=document.document_id,
                    user_id=user.user_id,
                )

            # If allow groups exist, they form an explicit whitelist. A match only lets evaluation continue; the classification rule must still pass.
            if allowed_groups and not user_groups & allowed_groups:
                return AuthorizationResult(
                    is_allowed=False,
                    reason=(
                        f"Access denied by explicit override on "
                        f"{document.document_id}: user does not "
                        f"belong to an allowed group."
                    ),
                    matched_rule="document_override_not_allowed",
                    document_id=document.document_id,
                    user_id=user.user_id,
                )

        # 3. Classification-level entitlement (always required)
        classification = document.classification
        rule = self.classification_rules.get(classification)

        if rule is not None:
            rule_id = rule["rule_id"]
            required_groups = rule["allow_groups"]
            matching_groups = user_groups & required_groups

            if matching_groups:
                return AuthorizationResult(
                    is_allowed=True,
                    reason=(f"Access granted by classification rule " f"'{rule_id}'."),
                    matched_rule=rule_id,
                    document_id=document.document_id,
                    user_id=user.user_id,
                )

            return AuthorizationResult(
                is_allowed=False,
                reason=(
                    f"Access denied by classification rule "
                    f"'{rule_id}': user does not satisfy the "
                    f"required group entitlement."
                ),
                matched_rule=rule_id,
                document_id=document.document_id,
                user_id=user.user_id,
            )

        # 4. No classification rule: apply the entitlements default_rule
        return AuthorizationResult(
            is_allowed=self.default_rule == "allow",
            reason=(
                f"Classification: '{classification}' has no authorization rule specified. default rule: '{self.default_rule}' applied."
            ),
            matched_rule=f"default_{self.default_rule}",
            document_id=document.document_id,
            user_id=user.user_id,
        )
