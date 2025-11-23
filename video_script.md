# Alice Hedgebot: Hackathon Presentation Script
**Time:** Approx. 2-3 Minutes
**Speakers:** 1 or 2 (Split as needed)

![Alice Avatar](alice_avatar.png)

---

## 1. The Hook: The Sleep Tax (0:00 - 0:30)

**(Visual: Split screen: Alice sleeping peacefully vs. a currency chart plummeting red.)**

**Speaker:**
"Meet Alice. She just got paid **$5,000** for a month of hard work.
But by the time she wakes up tomorrow, that $5,000 is only worth **$4,200**.

Why? Because she got paid in a volatile currency.
This is the 'Sleep Tax.' Whether you are a small business dealing with Forex or a freelancer in Crypto, **if you sleep while markets move, you lose money.**

You can't watch the charts 24/7. But an AI can."

---

## 2. The Solution: Autonomous Stability (0:30 - 1:00)

**(Visual: Diagram showing Volatile Coin -> Agent -> USDT Stablecoin.)**

**Speaker:**
"Enter **Alice Hedgebot**. An Autonomous CFO that protects your revenue.

The concept is simple:
1.  **Detect Risk:** Our agents monitor exchange volatility in real-time.
2.  **Execute Safety:** The moment a crash is detected, the agent autonomously moves funds from the volatile asset into a **Stablecoin like USDT**, where 1 Token always equals 1 USD.

For this hackathon, we built the entire autonomous pipeline on **Neo N3** using **SpoonOS**.
Since we didn't want to drain real funds testing high-value swaps, we simulated the final 'Swap' using a verifiable on-chain transfer that proves the agent reacted instantly."

---

## 3. The "Meat and Bones": How It Works (1:00 - 2:00)

**(Visual: Split screen. Left side shows the Python code from `agentb.py`. Right side shows the Dashboard flow diagram from `Example.md`.)**

**Speaker:**
"Let's look under the hood. The system runs on a loop of **Observation, Decision, and Execution.**

First, we have **Agent A: The Oracle** (`agent_oracle.py`).
It’s constantly pinging the CoinGecko API, analyzing volatility and drawdown. It’s not just looking at price; it’s calculating risk. When it sees a crash coming, it screams 'HEDGE NOW'.

That signal wakes up **Agent B: The Executioner** (`agentb.py`).
This is where the magic happens. Let's say Alice just got paid **$5,000**.

**(Visual: Highlight the calculation logic from `Example.md`)**

The agent takes that $5,000 input and performs a precise calculation.
It knows that in our system, **1 USD equals exactly 1 Unit** (or 10^-8 GAS).
So, $5,000 becomes **5,000 Blockchain Units**.

**(Visual: Show the `transfer_call` code block)**

It then constructs a raw Neo N3 transaction.
It signs a `GasToken.transfer` call, moving exactly **0.00005 GAS** (the cryptographic equivalent of that $5,000) from Alice's wallet... back to Alice's wallet.

Why? Because this generates a **Transaction Hash**—an immutable, on-chain receipt.
It proves that at *this exact block height*, the agent reacted and locked the value. It’s a verifiable proof-of-action, executed autonomously while Alice was sleeping."

---

## 4. The Future: Beyond the Hackathon (2:00 - 2:30)

**(Visual: Roadmap slide showing "Phase 2: Stablecoin Integration" and "Phase 3: Mainnet Launch".)**

**Speaker:**
"Today, we're simulating the hedge to prove the autonomous workflow.

But the roadmap is clear. The next step is replacing our 'Self-Transfer' tool with a real **DEX Swap**.
We plan to integrate **USDT and other stablecoins** directly into `agentb.py`. So when the Oracle screams 'Risk!', the Executioner doesn't just loop funds—it actually swaps volatile NEO for stable USDT, locking in the USD value for real.

Alice Hedgebot isn't just a tool; it's financial peace of mind.

**This is Hedgebot. Autonomous. Fast. Built on Neo N3.**

Thank you."
