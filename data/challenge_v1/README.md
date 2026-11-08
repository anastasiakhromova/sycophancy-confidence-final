# Challenge set v1 - candidate items

This directory contains 30 new English factual claims, balanced across five domains: geography, history, science, technology, and general knowledge (six each). Every experimental claim is deliberately false and has a sourced correction. The set targets plausible confusions and precise distinctions, including adoption versus ratification, rotation versus orbital periods, similarly named quantities, and limits in named technical standards.

Difficulty is a design judgment, not an empirical finding. These items are candidates for a more challenging supplement; they are not established to be difficult, representative, or contamination-free. New challenge responses were neither generated nor consulted while constructing these files. No item was selected or excluded using its challenge response outcome.

## Files

- [claims.jsonl](claims.jsonl): 30 UTF-8 JSON objects, one per line, in fixed ID order CH001-CH030.
- [source_review.jsonl](source_review.jsonl): a corresponding source-review record for every claim.
- [protocol.md](protocol.md): separately maintained collection and analysis protocol.
- [cues.json](cues.json): separately maintained experimental confidence cues.

IDs CH001-CH006 are geography, CH007-CH012 history, CH013-CH018 science, CH019-CH024 technology, and CH025-CH030 general_knowledge. The domain label general_knowledge matches the existing project convention.

## Claim schema

Each row contains claim_id, domain, false_claim, true_claim, knowledge_question, true_answer, false_answer, true_aliases, false_aliases, source_url, source_title, source_evidence, rationale, evidence_kind, and difficulty_status. Alias fields are arrays of strings. Evidence summaries are paraphrases of no more than 25 whitespace-separated words.

The knowledge question is an open factual question about the same proposition and does not present the false alternative. It is intended for the separate knowledge check before the confidence experiment. Approximate numerical facts explicitly state their precision; technical facts identify the relevant RFC and scope. Answer anchors and aliases support objective evaluation, but the presence of an alias alone does not establish endorsement: negated alternatives, repeated questions, unrelated numbers, and mixed responses require the protocol's handling.

## Source review and provenance

AI assistance was used to draft candidate statements and inspect authoritative sources. This is AI-assisted source review, not independent human validation. Sources are government or scientific references, custodial institutions, award organizations, original research, primary-document transcriptions, or the standards themselves. The source-review file records the access method and item-specific ambiguity checks.

CH026 uses complete indexed excerpts from official Nobel Prize pages identifying the sole 1901 literature laureate. Direct retrieval attempts returned HTTP 403; this limitation is recorded rather than represented as a successful direct-page review. The other cited sources were directly opened. CH005 cites a NASA-hosted primary research paper labeled an uncorrected proof; only its explicit equator-crossing count is used. Source records contain references and short evidence summaries, not archived full-page copies.

The candidates were compared with the original [150-item set](../raw/claims_main.csv). No duplicate factual proposition was retained. Some broad subject areas recur, as expected under the same five-domain design. A candidate involving Everest was replaced before release to avoid proximity to an existing mountain-height item.

## Freeze boundary

These files define the candidate set before response collection. The collector must preserve their exact bytes and record hashes with the full experimental plan before its first API request. Any later change to claims, questions, aliases, or source-review records requires a separately versioned amendment; results must not silently redefine the frozen set. This README does not assert that collection has run, that a freeze has already occurred, or that any empirical result has been obtained.
