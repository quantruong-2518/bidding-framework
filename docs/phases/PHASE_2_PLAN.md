# Phase 2: Full Pipeline (Weeks 5-8)

## Goal
Complete 11-state DAG, parallel agent execution, document parsing, human approval flow.

---

## Task 2.1: Complete 11-state DAG in Temporal
- Add states S3 through S11 to Temporal workflow
- Implement state transitions, feedback loops
- Conditional routing based on Bid Profile (S/M/L/XL)

## Task 2.2: Parallel Agent Execution (S3a, S3b, S3c)
- BA Agent, SA Agent, Domain Agent running as concurrent Temporal activities
- Cross-stream conflict detection
- Readiness tracking (>= 80% triggers convergence)
- Shared workspace for stream artifacts

## Task 2.3: Document Parsing Pipeline
- Unstructured.io integration for PDF/DOCX
- RFP parser: extract sections, requirements, tables
- Auto-populate Bid Card from parsed RFP

## Task 2.4: Human Approval Flow
- Temporal signals for approval/rejection
- Review UI in frontend (approve, reject with feedback, route to state)
- Notification system (email/webhook when approval needed)
- Timeout & escalation (configurable per bid profile)

## Task 2.5: Real-time Updates
- SSE for agent streaming (token-by-token output)
- WebSocket for workflow state transitions
- Redis Pub/Sub for Python workers -> NestJS -> Frontend

## Task 2.6: Bid Profile Routing
- S/M/L/XL profile configuration
- Dynamic pipeline: skip/simplify states based on profile
- Profile-specific review gate configuration

## Task 2.7: Bid Workspace in Obsidian
- Auto-create bid folder structure when bid starts
- AI output writes to vault as markdown
- Bi-directional sync: vault changes -> re-index
