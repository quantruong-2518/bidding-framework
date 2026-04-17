---
name: new-state
description: Add a new state to the Temporal bid workflow
allowed-tools: Bash(ls*) Read Write Edit
---

# Add New State to Bid Workflow

Arguments: $ARGUMENTS (state ID and name, e.g. "S5 solution-design")

## Steps

1. Read state spec from `docs/states/STATE_MACHINE.md` for the requested state

2. Read current workflow: `src/ai-service/workflows/bid_workflow.py`

3. Create activity for the state at `src/ai-service/activities/`:
   - Input model (from previous state output)
   - Output model (for next state input)
   - Activity function with LangGraph agent call

4. Add state to workflow:
   - Add activity call in correct position
   - Wire transitions (including feedback loops if any)
   - Handle bid profile conditions (skip/simplify for S/M/L/XL)

5. Create test at `src/ai-service/tests/test_<state>.py`

6. Update `CURRENT_STATE.md` with progress.
