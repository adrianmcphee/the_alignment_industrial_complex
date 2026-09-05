# Change log

## v0.3 companion refresh for book v2.0.5 - 5 September 2026

- Updated the companion reference to the book's v2.0.5 review edition.
- Increased the front-cover subtitle line spacing by 10 per cent.

The manuscript wording, back cover and Field Guide protocol are unchanged.
The protocol remains v0.3; this is a cover-spacing refresh only.

## v0.3 companion refresh for book v2.0.4 - 5 September 2026

- Updated the companion reference to the book's v2.0.4 review edition.
- Refreshed the front-cover artwork with a mixed-case subtitle, preserving
  the book's title and subtitle wording and the existing back cover.
- Refreshed the guide distribution and checksums alongside the book build.

The protocol remains v0.3. Its schema and rule-set versions, validation
contracts and reuse-licence notice are unchanged.

## v0.3 distribution refresh - 5 September 2026

- Updated the companion book identity to *The Alignment-Industrial Complex:
  How Fragmented Authority Destroys a Company's Ability to Compete*, review
  edition v2.0.3.
- Updated the public repository reference to
  `adrianmcphee/the_alignment_industrial_complex`.
- Refreshed the exported worked examples, validation record, PDF, source
  archive and checksums from the book's current guide build.
- Added stable root PDF and source-archive links alongside the versioned
  release copies, and refreshed the front and back cover artwork.
- Corrected the repository's public-availability notice without granting a
  software, documentation or artwork reuse licence.

The protocol remains v0.3. Schema and rule-set versions are unchanged; this
refresh updates the distribution and companion-book references.

## 0.3 - 26 August 2026

- Published the YAML artefacts as usable files and made those files the source
  of the PDF listings.
- Added durable identity and schemas for the evidence envelope, change
  mechanics, and validation rule set.
- Generalised evidence joins around `process_cycle_id`, with explicit renewal
  bindings to `renewal_cycle_id` and `policy_id`.
- Changed the core validation rule set to 2.0.0 because V010, V016, and V019
  changed meaning.
- Added V021 through V025 and warning rules W001 through W004.
- Moved model-evaluation and process-definition schemas to 2.0.0 so threshold
  direction and structured transition publication are enforceable.
- Added maturity support to the evaluation, charter, and drift schemas.
- Added process-to-contract and charter-to-process linkage checks.
- Allowed a drift finding to record an `evidence_gap` when neither running
  behaviour nor a production sample can yet be established.
- Clarified drift-report identity and version changes.
- Added four broken fixtures. Three fail as expected; one known institutional
  resolution gap remains open by design.
- Added rule-set, schema-version, and canonical validation-archive provenance
  to the validation record. The PDF carries the distribution archive digest.
- Clarified why portable and renewal-domain keys are emitted together, and
  limited `maturity.mandatory_now` to obligations beyond schema conformance.

Validation result: eight schema contracts and eleven governed artefacts passed
schema validation; no error rule failed; W003 warned on two overdue worked
findings; V023 and W004 were not applicable to the supplied packet.
