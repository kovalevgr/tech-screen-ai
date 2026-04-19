# Assessor — v0001 — notes

## What changed

Initial version.

## Why

Establish a baseline Assessor prompt calibrated against the Correctness Variant A rules (ADR-020): coverage:wrong + `FACTUALLY_WRONG` red flag, levels 1–4, confidence ∈ [0, 0.99].

## Design choices worth noting

- **JSON strict mode.** Output is strictly schema-validated in the Vertex adapter. Any deviation raises `LLMSchemaError`.
- **Rationale in English.** The Assessor is English-only; only the candidate answers may be non-English. This makes review, diff, and corpus analysis uniform.
- **No 1.0 confidence.** Floor of 0.0, ceiling of 0.99. Perfect confidence is a calibration smell — the Assessor has been observed in pilots to anchor high when given the option.
- **Empty assessments are valid.** A terse candidate answer does not produce a level assessment; it produces an empty array and a note.
- **Red flags orthogonal to levels.** Factually wrong L3 reasoning is both an L3 and a red flag. We preserve the signal rather than collapse it.
- **Evidence spans must be exact substrings.** Paraphrasing hides drift; exact quotes make downstream review trivial.

## Hypothesised behaviour

- Initial exact-match to human ground truth: 0.55–0.70 per competency. Below that, we adjust the rubric or the prompt; above 0.85 on day one is suspicious.
- Systematic bias: expect a slight over-assignment of L2 (the "middle" default). Calibration will surface this.
- Red-flag precision: target > 0.80 at MVP. Recall is secondary — we'd rather miss some than flag the wrong thing.

## Known risks

- **Confident-and-wrong outputs.** The model may assign a level with 0.85 confidence while the descriptor match is actually borderline. Mitigation: confidence cap + rationale review.
- **Evidence span fabrication.** The model may quote paraphrased text; the schema requires minLength 1 but does not enforce "substring of input". We plan a post-validator in the adapter that checks the span is actually in the candidate answer.
- **Russian answers.** When the candidate replies in Russian, the Assessor must still produce English output. The prompt forbids Ukrainian/Russian in any field; calibration will confirm.

## Calibration delta

N/A — initial version.

## Author

Ihor — 2026-04-18.
