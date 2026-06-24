# Specification Quality Checklist: Position Template schema + contract (T12)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-24
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- This is a data-model + contract task, so the spec necessarily names existing
  domain entities (`position_template`, `stack`, `competency`, `archived_at`)
  and the §14 contract deliverables (JSON schema, OpenAPI). These are treated as
  the *subject* of the feature, not as prescribed implementation — the
  Functional Requirements stay capability-focused (WHAT must hold), and HOW
  (column types, FK strategy, migration shape) is deferred to `plan.md`.
- Zero `[NEEDS CLARIFICATION]` markers: ambiguities were resolved with informed
  defaults and recorded in **Assumptions**. Three of those defaults are worth an
  explicit confirmation at the gate (see the handoff message): (1) rubric
  reference-by-id with snapshotting deferred to T15; (2) `level` as a fixed role
  enum distinct from the rubric `level` rows; (3) competency-belongs-to-selected-stack
  as a hard validation rule. If the user disagrees with any, run
  `speckit-clarify` before `speckit-plan`.
- All items pass on the first validation iteration. Spec is ready for
  `speckit-clarify` (optional) or `speckit-plan`.
