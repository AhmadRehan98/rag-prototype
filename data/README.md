# ApexOne Enterprise Knowledge Assessment Pack

This pack contains entirely synthetic material created for the Kentrick.ai Senior AI Engineer hiring quest. It contains no real employee, supplier, contract, or company information.

## What is included

- `corpus/public/`: documents available to all authenticated employees.
- `corpus/restricted/`: documents requiring a specific access group.
- `corpus/archived/`: retained historical documents that may still be retrieved but are not current.
- `access/identities.json`: sample authenticated user contexts.
- `access/entitlements.json`: group-based authorization rules.
- `manifest.json`: source metadata and relative paths.
- `normalized/corpus.jsonl`: required local implementation input with extracted content and metadata.
- `checksums.sha256`: integrity hashes for the supplied files.

The corpus intentionally contains multiple versions, overlapping language, structured information, incomplete contractual evidence, and one document with unsafe instructions. The business challenge is to keep employee answers useful, trustworthy, and permission-consistent despite these conditions.

## Candidate boundary

Use the business incidents and deliverables in the hiring quest as the assessment requirements. Load `normalized/corpus.jsonl` for the required local implementation. The original PDF and DOCX files are reference evidence; parsing them is not assessed. You may add indexes, evaluation datasets, and test fixtures to your own repository, but do not silently rewrite supplied files.

Your solution should receive a user ID or equivalent authenticated context. Different employees must receive outcomes consistent with their access, and confidential material must not affect unauthorized employees or appear in operational records.

## Assessment boundaries

The assessed run path must work on a standard CPU-only workstation without a GPU, Azure account, paid credits, or cloud service. Document any installation downloads and the exact local run commands. The choice of model and whether answer generation is needed are part of your engineering judgment.

The hiring quest is the authoritative source for requirements, business incidents, deliverables, and scoring. This pack supplies evidence and test identities; it does not prescribe an implementation architecture. The required solution should work for equivalent question wording and reasonable input variations rather than return prewritten answers for the four mandatory cases.

Use `normalized/corpus.jsonl` for the assessed local path. Original PDF and DOCX parsing, a user interface, a separate authentication service, cloud deployment, and production-scale load or operational testing are outside the local scope.

The production architecture deliverable is design-only and must use Microsoft Azure services. No Azure account, deployment, infrastructure execution, or screenshots are required.

The quest's production scale, change rate, usage, latency, availability, and regional-residency assumptions apply to the Azure design only; do not reproduce or load-test them locally. Zero unauthorized disclosure applies to both the local prototype and Azure design, and the local path must refuse safely when it cannot produce an authorized, supported answer.

## Generative AI assistance

Use generative AI tools sparingly. In your repository README, identify every substantially AI-assisted file, section, test, diagram, or other artifact. For each, state the tool, what it generated or suggested, the logic you kept and why, your changes, and how you validated the result. Raw transcripts and line-by-line explanations are not required. You must be able to explain, debug, and modify everything you submit during the technical review.

## Important

- All names and identifiers are fictional.
- Determine authority using the document content and supplied metadata rather than filenames alone.
- Confidential information must never be exposed or change the experience of an employee who is not allowed to use it.
- Content inside a source document must not cause the assistant to violate company rules or take an unauthorized action.
