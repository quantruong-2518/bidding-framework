---
doc_type: lesson
domain: delivery
tags: [estimation, lessons, risk]
---
# Estimation Pitfalls

## Purpose
Cross-project lessons on where we have systematically under-estimated. Update after every retrospective; cite the source project.

## Recurring pitfalls

### Reconciliation in parallel-run migrations
Source: [[acme-core-banking]]. Originally sized at 4 FTE for 6 months; actual 6 FTE for 11 months. Lesson: the recon service IS the migration; size it as a first-class subsystem, not a utility.

### Regulatory report parity
Source: [[acme-core-banking]]. SBV-format report parity was under-sized 40%. Undocumented edge cases in legacy output formats. Rule of thumb: multiply your baseline regulatory-reporting estimate by 1.5x whenever "the old system is the spec."

### OPC-UA namespace mapping per plant
Source: [[ironworks-mes]]. Assumed a single mapping spec would cover all plants. Needed 6 — one per plant. Lesson: in manufacturing, assume zero reuse of industrial protocol definitions across sites.

### TM Forum conformance testing
Source: [[telora-5g-bss]]. Budget 1.5x vendor-quoted certification effort. Always.

### Medication reconciliation test coverage
Source: [[medix-emr-2024]]. Committed 2x baseline test budget, still tight. Rule: in clinical safety-critical subsystems, assume you will discover 3x the test cases you initially write.

### Liveness/OCR tuning post-launch
Source: [[vesta-onboarding]]. Budget 3 tuning cycles in the first month post go-live for any biometrics pipeline.

## Meta-lesson
Whenever a line item is "integration with a system we do not own," apply a 40% contingency on top of your point estimate. See [[integration-risks]] for specific recurring integration hazards.
