# 🤖 Alice Hedgebot: The Autonomous CFO

> **The Problem:** "The Sleep Tax."
> Whether you are a small business dealing with Forex or a freelancer in Crypto, if you sleep while markets move, you lose money.

---

## 1. The Architecture
We built a multi-agent system on **SpoonOS** that acts as a 24/7 bodyguard for your wallet.

*   **Agent A (The Oracle):** Watches the market for volatility.
*   **Agent B (The Executioner):** Moves funds to safety when risk is detected.

---

## 2. Agent A: The Watchtower (Oracle)
**Real World Logic:**
Just like a human trader watching charts, this agent pings market APIs (CoinGecko) to calculate a "Risk Score." It doesn't just look at price; it looks at **volatility** and **drawdown**.

**The Code:**
```python
# alice-hedgebot/agents/agent_oracle.py

def fetch_market_risk(asset_symbol: str = "neo") -> MarketRiskReport:
    # ... fetch data from CoinGecko ...
    
    # 1. Drawdown: How much has it crashed today?
    drawdown_pct = ((high_24h - price) / high_24h) * 100
    
    # 2. Volatility: How wild are the swings?
    volatility_pct = ((high_24h - low_24h) / price) * 100
    
    # DECISION LOGIC
    if (drawdown_pct > 0.1) or (volatility_pct > 0.1):
        return MarketRiskReport(risk_level="CRITICAL", recommendation="HEDGE_NOW")
    
    return MarketRiskReport(risk_level="LOW", recommendation="HOLD")
```

---

## 3. Agent B: The Executioner
**Real World Logic:**
When the Oracle screams "HEDGE_NOW", this agent wakes up. Its job is to take the USD value you want to protect (e.g., $5,000) and lock it on the blockchain.

**The Hackathon Simulation:**
For this demo, instead of swapping to USDT (which requires liquidity pools), we perform a **Self-Transfer**. This generates a verifiable **Transaction Hash** on Neo N3, proving the agent reacted instantly.

**The Math (Hackathon Logic):**
We use a precise rule: `1 USD = 1 Unit (10^-8 GAS)`.
*   Input: **$5,000**
*   Blockchain Move: **5,000 Units** (0.00005 GAS)

**The Code:**
```python
# alice-hedgebot/agents/agentb.py

async def execute(self, amount_usd: float) -> dict:
    # 1. Convert USD to Blockchain Units
    # Rule: 1 USD = 10^-8 GAS (1 Integer Unit)
    units_to_move = int(amount_usd) 
    
    # 2. Construct the Transaction (The "Hedge")
    transfer_call = gas_token.transfer(
        source=account.script_hash,      # From Alice
        destination=account.script_hash, # To Alice (Safe Loop)
        amount=units_to_move,            # 0.00005 GAS
        data=None
    )
    
    # 3. Sign & Broadcast to Neo N3
    tx_hash = await facade.invoke_fast(transfer_call, signers=[signing_pair])
    
    return {
        "status": "SUCCESS", 
        "tx_hash": str(tx_hash), 
        "gas_locked": units_to_move / 100_000_000
    }
```

---

## 4. Translation to Real World
How does this code change for the Mainnet product?

| Feature | Hackathon Code | Real World Code |
| :--- | :--- | :--- |
| **Action** | `gas_token.transfer(self, self)` | `router.swapToken(NEO, USDT)` |
| **Math** | `1 USD = 1 Unit` | `1 NEO = $X (Oracle Price)` |
| **Result** | Proof of Reaction Time | Stablecoin Balance (Value Locked) |

**The Vision:**
By simply swapping the `transfer` function with a `swap` function, Alice Hedgebot evolves from a demo into a fully functional **Autonomous CFO** that saves businesses 3-5% in lost revenue annually.
