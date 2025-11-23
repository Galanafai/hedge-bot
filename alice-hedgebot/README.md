# Alice HedgeBot

## Overview

`alice-hedgebot` is a prototype of an autonomous hedging system built on the Neo N3 blockchain. It consists of two primary agents:

1. **Execution Agent (Agent B)** – Exposes a FastAPI `/hedge` endpoint that executes an on‑chain GAS transfer using a user‑specified USD amount.
2. **Oracle Agent** – Provides a `/market‑risk` endpoint that fetches real‑time market data from CoinGecko, calculates a risk score, and recommends whether to **HOLD** or **HEDGE_NOW**.

Both agents are built with the **SpoonAI SDK** (`BaseTool`, `ToolCallAgent`, `ToolManager`) and use **Pydantic** models for request/response validation.

## Current State

- `agents/agentb.py` – Implements `HedgeTool` and `ExecutionAgent` with a FastAPI server on port **8001**.
- `agents/agent_oracle.py` – Implements `MarketRiskTool` and `OracleAgent` with a FastAPI server on port **8000**.
- `test_trigger.py` – Simple script that verifies the Oracle's force‑trigger logic.
- Development environment is running:
  - `n8n` workflow engine (`npx n8n start`).
  - Virtual environment activated (`source venv/bin/activate`).
  - Python processes for the agents are running.

## How to Run Locally

```bash
# Activate the virtual environment
source venv/bin/activate

# Run the Oracle (port 8000)
python -m alice-hedgebot.agents.agent_oracle

# In another terminal, run the Execution Agent (port 8001)
python -m alice-hedgebot.agents.agentb
```

You can then call the endpoints, e.g.:

```bash
# Hedge $10
curl -X POST http://localhost:8001/hedge -H "Content-Type: application/json" -d '{"amount_usd":10}'

# Get market risk for NEO
curl http://localhost:8000/market-risk?asset_symbol=neo
```
