## How to run:

- pull the repo locally, in the root dir, do the following commands:
- docker compose up -d
- docker compose exec api poetry run alembic upgrade head
- docker compose exec api poetry run python -m scripts.seed_data
- docker compose exec api poetry run python -m pytest

## Assumptions/Limitations:

- Authorization rules are ANDed. Every point is checked in this order. If any step fails, the auth rejects the request:
  1. The user is not in any of the document's deny groups.
  2. If the document has an allow list, the user is in it. (No allow list: check skipped.)
  3. If the document's classification has a rule, the user is in one of its allowed groups.
  4. If the classification has no rule, "default_rule" is checked. "default_rule" only stands in for a missing classification rule, and an allow override can narrow access but never grant what the classification rule denies. If there is no "default_rule" mentioned I assume it's a deny to enhance security.

  The assumption here is on the "default_rule". I could instead make it so "default_rule": "allow" means always allow unless there's an explicit denial mentioned, and "deny" means always deny unless there's an explicit allowance. Currently instead, "default_rule" only applies if the classification rule is missing.
