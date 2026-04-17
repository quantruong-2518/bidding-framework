# State Machine — AI Bidding Framework

> **Implementation status (2026-04-17, Phase 2.1 delivered):**
> - **S0/S1/S2** are live with real heuristic logic in `activities/{intake,triage,scoping}.py`.
> - **S3a/b/c + S4..S11** are live with deterministic stubs (`activities/stream_stubs.py` + `activities/{convergence,solution_design,wbs,commercial,assembly,review,submission,retrospective}.py`).
> - Workflow terminal is `S11_DONE`; `S1_NO_BID` still fires on reject or 24h gate timeout.
> - All state literals (`S0..S11_DONE` incl. `S1_NO_BID` / `S2_DONE`) live in `workflows/base.py::WorkflowState`; frontend mirror is `src/frontend/lib/utils/state-palette.ts`.
> - The **feedback loops** (S9 reject → S8/S6/S5/S2, S6 over-budget → S5/S4, etc.) are documented below but **not yet wired** in the workflow — Phase 2.4 owns that.
> - Real LLM agents for S3a/b/c + real conflict detection at S4 are Phase 2.2 (blocked on `ANTHROPIC_API_KEY`).
> - See `docs/phases/PHASE_2_PLAN.md` for scope + delivery notes.

## Overview

```
S0 INTAKE
   |
   v
S1 TRIAGE ──── no-bid ──> END (luu ly do)
   |
   v
S2 SCOPING
   |
   v
S3 PARALLEL STREAMS ════════════════════════════╗
   ║                                             ║
   ║  S3a Business    S3b Technical   S3c Domain ║
   ║  Analysis        Analysis        Mining     ║
   ║       |               |              |      ║
   ║       └───────┬───────┘──────────────┘      ║
   ║               v                             ║
   ║        S4 CONVERGENCE                       ║
   ╚═════════════════════════════════════════════╝
               |
               v
        S5 SOLUTION DESIGN
               |
               v
        S6 WBS + ESTIMATION
               |
               v
        S7 COMMERCIAL STRATEGY
               |
               v
        S8 ASSEMBLY
               |
               v
        S9 REVIEW GATE ──── reject ──> loop back (co chi dinh state)
               |
               v
        S10 SUBMISSION
               |
               v
        S11 RETROSPECTIVE ──> feed back vao Knowledge Base
```

## Feedback Loops

```
S9 reject      --> S8 (minor) / S6 (WBS) / S5 (solution) / S2 (scope)
S6 over-budget --> S5 (simplify) / S4 (re-scope)
S4 conflicts   --> S3x (stream cu the can rework)
S7 unfeasible  --> S6 (re-estimate) / S5 (re-design)
S11 lessons    --> S0 KB (long-term improvement)
```

## Bid Profiles

```
Bid S  (< 100 MD):     S0 > S1 > S2 > S3a,S3b > S4 > S6 > S8 > S9(1) > S10
Bid M  (100-500 MD):   Full pipeline, S3c lightweight
Bid L  (500-2000 MD):  Full pipeline, 3/5 review gate
Bid XL (> 2000 MD):    Full + S3d,S3e + multi-gate + C-level approval
```

## State Matrix

```
┌──────┬─────────────────────┬──────────┬───────────┬──────────┬─────────────────┐
│State │ Name                │Parallel? │ Bid S     │ Bid XL   │ Status (2.1)    │
├──────┼─────────────────────┼──────────┼───────────┼──────────┼─────────────────┤
│ S0   │ Intake              │ No       │ simple    │ full     │ REAL heuristic  │
│ S1   │ Triage              │ No       │ quick     │ deep     │ REAL heuristic  │
│ S2   │ Scoping             │ No       │ light     │ full     │ REAL heuristic  │
│ S3a  │ Business Analysis   │ YES      │ YES       │ YES      │ STUB*           │
│ S3b  │ Technical Analysis  │ YES      │ YES       │ YES      │ STUB            │
│ S3c  │ Domain Mining       │ YES      │ SKIP      │ YES      │ STUB            │
│ S3d  │ Competitive Intel   │ YES      │ SKIP      │ YES      │ — (Phase 3)     │
│ S3e  │ Resource & Capacity │ YES      │ SKIP      │ YES      │ — (Phase 3)     │
│ S4   │ Convergence         │ No       │ simple    │ full     │ STUB            │
│ S5   │ Solution Design     │ No       │ light     │ full     │ STUB            │
│ S6   │ WBS + Estimation    │ No       │ YES       │ YES      │ STUB            │
│ S7   │ Commercial Strategy │ No       │ SKIP      │ YES      │ STUB            │
│ S8   │ Assembly            │ No       │ template  │ custom   │ STUB            │
│ S9   │ Review Gate         │ No       │ 1 reviewer│ multi    │ STUB (auto-ok)  │
│ S10  │ Submission          │ No       │ YES       │ YES      │ STUB            │
│ S11  │ Retrospective       │ No       │ basic     │ deep     │ STUB            │
└──────┴─────────────────────┴──────────┴───────────┴──────────┴─────────────────┘

Legend:
  REAL = deterministic heuristic, no LLM
  STUB = Phase 2.1 deterministic placeholder (swapped to real LLM in 2.2 or later)
  SKIP = not applicable for this bid profile (Phase 2.6 wires the conditional routing)

* S3a: the LangGraph BA agent (`agents/ba_agent.py` + `activities/ba_analysis.py`)
  is fully implemented but sits dormant — `ba_analysis_stub_activity` runs in
  its place until Phase 2.2 swaps the three stream activities.
```

## Implementation Pointers

| Concern | File |
|---|---|
| Workflow orchestration (S0 → S11_DONE) | `src/ai-service/workflows/bid_workflow.py` |
| State literals (`WorkflowState`) | `src/ai-service/workflows/base.py` (re-exported by `workflows/models.py`) |
| S3..S11 artifact DTOs | `src/ai-service/workflows/artifacts.py` |
| S0 intake activity | `src/ai-service/activities/intake.py` |
| S1 triage activity (+ stub scorer) | `src/ai-service/activities/triage.py` + `agents/triage_agent.py` |
| S1 human gate (signal/query/timeout) | `bid_workflow.py` — `human_triage_decision` signal, `get_state` query, 24h wait |
| S2 scoping activity | `src/ai-service/activities/scoping.py` |
| S3a/b/c stream stubs | `src/ai-service/activities/stream_stubs.py` |
| S3a real BA agent (dormant) | `src/ai-service/agents/ba_agent.py` + `activities/ba_analysis.py` |
| S4 convergence stub | `src/ai-service/activities/convergence.py` |
| S5 HLD stub | `src/ai-service/activities/solution_design.py` |
| S6 WBS stub | `src/ai-service/activities/wbs.py` |
| S7 commercial stub | `src/ai-service/activities/commercial.py` |
| S8 assembly stub | `src/ai-service/activities/assembly.py` |
| S9 review stub | `src/ai-service/activities/review.py` |
| S10 submission stub | `src/ai-service/activities/submission.py` |
| S11 retrospective stub | `src/ai-service/activities/retrospective.py` |
| Worker registration | `src/ai-service/worker.py` (task queue `bid-workflow-queue`) |
| HTTP trigger surface (ai-service) | `src/ai-service/workflows/router.py` (`/start`, `/start-from-card`, `/{id}/triage-signal`, `/{id}`) |
| NestJS artifact endpoint | `src/api-gateway/src/workflows/workflows.controller.ts` (`GET /bids/:id/workflow/artifacts/:type`) |
| Frontend state palette | `src/frontend/lib/utils/state-palette.ts` |
| Frontend DAG | `src/frontend/components/workflow/workflow-graph.tsx` |
| Frontend artifact panels | `src/frontend/components/workflow/state-detail.tsx` |

---

## Detailed State Descriptions

### S0: INTAKE — Tiep nhan co hoi

```
Trigger:    RFP/RFI upload, hoac manual tao opportunity
AI lam:     Parse document -> extract metadata tu dong
Output:     Bid Card (structured data)
```

**Bid Card bao gom:**
- Client name, industry, region
- Deadline & timeline constraints
- Scope summary (auto-extracted)
- Technology keywords detected
- Estimated bid size (S/M/L/XL) — AI de xuat, nguoi duyet
- Danh sach requirements (raw, chua phan loai)

---

### S1: TRIAGE — Quyet dinh Bid/No-Bid

```
Trigger:    Bid Card hoan tat
AI lam:     Scoring tu dong dua tren multi-criteria
Output:     Bid/No-Bid recommendation + score breakdown
Gate:       Bid Manager quyet dinh cuoi
```

**AI Scoring Criteria:**
- Win probability (lich su win/loss voi client, domain)
- Resource availability (query resource pool)
- Technical fit (match tech stack vs capability)
- Strategic value (client tier, market segment)
- Timeline feasibility (deadline vs estimated effort)

**Bid Profile duoc set o day:** S / M / L / XL

---

### S2: SCOPING — Phan ra & Chuan bi

```
Trigger:    Bid approved
AI lam:     Decompose RFP thanh requirement atoms
Output:     Requirement Map + Stream Assignment + Team Setup
```

3 viec chinh:
1. **Requirement Decomposition** — functional, NFR, technical, compliance, timeline, unclear
2. **Stream Assignment** — AI de xuat requirement nao thuoc stream nao
3. **Team Assembly** — De xuat team composition theo bid profile

---

### S3: PARALLEL STREAMS — Da tuyen kien thuc chay dong thoi

**S3a: BUSINESS ANALYSIS STREAM**
- Owner: BA | Agent: Business Analyst Agent
- Input: Functional requirements + client context
- Output: Business Requirements Document, Assumptions & Constraints

**S3b: TECHNICAL ANALYSIS STREAM**
- Owner: SA | Agent: Solution Architect Agent
- Input: Technical requirements + NFRs + constraints
- Output: Technology Stack recommendation, Technical risks, Architecture patterns

**S3c: DOMAIN KNOWLEDGE STREAM**
- Owner: Domain Expert | Agent: Domain Mining Agent
- Input: Industry/domain requirements
- Output: Domain constraints, Compliance checklist, Best practices

**S3d: COMPETITIVE INTELLIGENCE STREAM** (XL only)
- Owner: Bid Manager | Agent: Intelligence Agent
- Output: Win themes, Competitive positioning, Price sensitivity

**S3e: RESOURCE & CAPACITY STREAM**
- Owner: PM | Agent: Capacity Agent
- Output: Resource availability matrix, Skill gap analysis

**Cross-stream sync:**
- Moi stream publish artifacts len shared workspace
- AI detect cross-stream conflicts
- Convergence bat dau khi tat ca >= 80% readiness

---

### S4: CONVERGENCE — Hoi tu & Giai quyet xung dot

```
Trigger:    Tat ca active streams >= 80% readiness
AI lam:     Merge outputs, detect conflicts, propose resolutions
Output:     Unified Project Understanding (UPU)
Gate:       Bid Manager + key stream owners confirm
```

Steps: MERGE -> CONFLICT DETECTION -> RESOLUTION PROPOSALS -> UNIFIED OUTPUT

---

### S5: SOLUTION DESIGN

```
Trigger:    UPU confirmed
AI lam:     Generate HLD draft, architecture diagrams
Output:     HLD, Architecture diagrams, Integration design, Security approach
Nguoi:      SA lead, BA + Domain Expert review
```

---

### S6: WBS + ESTIMATION

```
Trigger:    Solution Design approved
AI lam:     Generate WBS draft, estimate effort per item
Output:     WBS + Effort Estimation + Timeline
```

3 layers:
1. **AI DRAFT** — generate tu similar past projects + templates
2. **HUMAN CALIBRATION** — SA/BA adjust, tracked (AI vs Human delta)
3. **AI VALIDATION** — cross-check vs similar projects, missing tasks, timeline feasibility

---

### S7: COMMERCIAL STRATEGY

```
Trigger:    WBS + Estimation approved
AI lam:     Price modeling, scenario analysis (ADVISORY ONLY)
Output:     Pricing Model + Negotiation Brief
```

---

### S8: ASSEMBLY

```
Trigger:    Commercial strategy approved
AI lam:     Compile & format all documents
Output:     Complete Proposal Package (PDF/DOCX/HTML)
```

Steps: COMPILE -> CONSISTENCY CHECK -> QUALITY ENHANCEMENT -> FORMAT

---

### S9: REVIEW GATE

```
Bid S:  1 reviewer
Bid M:  Technical + Business review -> Final review
Bid L:  5 reviews -> Bid Committee (3/5 vote)
Bid XL: Committee + Executive Gate (C-level)
```

Reject kem: specific feedback, severity, target state to loop back.

---

### S10: SUBMISSION

```
Trigger:    Final approval
Output:     Submitted proposal + confirmation
```

Auto-checklist: all sections complete, compliance 100%, pricing signed, format correct, deadline check.

---

### S11: RETROSPECTIVE

```
Trigger:    Bid result announced (win/loss)
AI lam:     Analysis, extract lessons, update KB
```

- WIN: save winning patterns, pricing sweet spots, update estimation model
- LOSS: save loss patterns, competitor insights, update triage scoring
- DELIVERED (post-project): actual vs estimated -> update estimation benchmarks
