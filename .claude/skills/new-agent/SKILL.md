---
name: new-agent
description: Scaffold a new LangGraph agent with Temporal activity wrapper
allowed-tools: Bash(ls*) Read Write Edit
---

# Create New LangGraph Agent

Arguments: $ARGUMENTS (agent name, e.g. "sa" for Solution Architect Agent)

## Steps

1. Read existing agent as reference:
```
src/ai-service/agents/ba_agent.py
```

2. Create new agent file at `src/ai-service/agents/$0_agent.py` following the same pattern:
   - LangGraph StateGraph definition
   - Tools (KB search, Claude client)
   - Nodes for each reasoning step
   - Compiled graph

3. Create Temporal activity wrapper at `src/ai-service/activities/$0.py`:
   - Async activity function
   - Input/output Pydantic models
   - Error handling with structured logging

4. Create test at `src/ai-service/tests/test_$0_agent.py`

5. Register the activity in `src/ai-service/workflows/bid_workflow.py`

6. Update `CURRENT_STATE.md` with progress.
