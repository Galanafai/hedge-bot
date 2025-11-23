import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from spoon_ai.tools.base import BaseTool
from spoon_ai.agents import ToolCallAgent
from spoon_ai.tools import ToolManager
from spoon_ai.llm.base import LLMBase
from spoon_ai.schema import LLMResponse

# NEO N3 IMPORTS
from neo3.wallet.account import Account
from neo3.api.wrappers import GasToken, ChainFacade
from neo3.network.payloads.verification import WitnessScope
from neo3.api.helpers.signing import sign_with_account
from neo3.network.payloads.verification import Signer
import httpx

# --- 1. DEFINE THE HEDGE TOOL ---
class HedgeTool(BaseTool):
    name: str = "execute_hedge"
    description: str = "Hedges the specified USD amount by performing a REAL transaction on Neo N3."
    parameters: dict = {
        "type": "object",
        "properties": {
            "amount_usd": {
                "type": "number",
                "description": "The dollar value to hedge (e.g. 5000.0)"
            }
        },
        "required": ["amount_usd"]
    }

    async def execute(self, amount_usd: float) -> dict:
        """Execute the hedge transaction"""
        # --- CONFIGURATION ---
        # Your specific WIF (TestNet Wallet)
        WIF = "Kz63tuUgq54jWyZ14h8pZQq6kDU7fXidxLipp4QUFvYKfPGYLeUS"
        RPC_URL = "http://seed1t5.neo.org:20332"

        print(f"🤖 AGENT WAKING UP: Initiating Hedge for ${amount_usd}...")

        # --- THE HACKATHON MATH (DO NOT CHANGE) ---
        # Rule: 1 USD = 1 Unit (0.00000001 GAS)
        # Example: Input $10,000 -> 10,000 integer units (Satoshis)
        # This allows 'Micro-Hedging' without draining the wallet.
        units_to_move = int(amount_usd)
        
        # Calculate human-readable value for the Dashboard (e.g. 0.0001 GAS)
        # 1 GAS = 100,000,000 units
        human_readable_gas = units_to_move / 100_000_000

        try:
            # A. Connect to Neo N3 Node
            facade = ChainFacade(RPC_URL)
            account = Account.from_wif(WIF)
            print(f"✅ Wallet Authenticated: {account.address}")

            # B. Fetch Block Height (Critical for Dashboard)
            # We fetch this LIVE so the UI doesn't say "undefined"
            # block_height = await facade.rpc.get_block_count()
            async with httpx.AsyncClient() as client:
                resp = await client.post(RPC_URL, json={
                    "jsonrpc": "2.0",
                    "method": "getblockcount",
                    "params": [],
                    "id": 1
                })
                block_height = resp.json()["result"]

            # C. Create Self-Transfer (The "Hedge" Action)
            gas_token = GasToken()
            transfer_call = gas_token.transfer(
                source=account.script_hash,
                destination=account.script_hash,
                amount=units_to_move,
                data=None
            )

            print("🔄 Constructing and Signing Transaction...")

            # D. Sign & Broadcast
            signer = Signer(account.script_hash, WitnessScope.CALLED_BY_ENTRY)
            signing_function = sign_with_account(account)
            signing_pair = (signing_function, signer)
            
            tx_hash = await facade.invoke_fast(transfer_call, signers=[signing_pair])
            
            print(f"🚀 TRANSACTION SENT! Hash: {tx_hash}")
            
            # E. RETURN RICH DATA (For Dashboard)
            return {
                "status": "SUCCESS",
                "tx_hash": str(tx_hash),
                "gas_locked": human_readable_gas,  # The exact calculation
                "units_moved": units_to_move,
                "block_height": block_height,      # Real block height
                "wallet": account.address
            }

        except Exception as e:
            print(f"⚠️ TRANSACTION ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "status": "ERROR",
                "error": str(e),
                "gas_locked": 0,
                "block_height": 0
            }

# --- DUMMY LLM (Required for SpoonOS ToolCallAgent) ---
class DummyLLM(LLMBase):
    async def chat(self, messages, **kwargs): return LLMResponse(content="Dummy")
    async def completion(self, prompt, **kwargs): return LLMResponse(content="Dummy")
    async def chat_with_tools(self, messages, **kwargs): return LLMResponse(content="Dummy")

# --- 2. DEFINE THE AGENT ---
class ExecutionAgent(ToolCallAgent):
    name: str = "Alice's Executioner (Agent B)"
    description: str = "An autonomous agent that secures funds on the Neo Blockchain."
    llm: LLMBase = Field(default_factory=lambda: DummyLLM())
    available_tools: ToolManager = Field(
        default_factory=lambda: ToolManager([HedgeTool()])
    )

# --- 3. EXPOSE VIA FASTAPI ---
app = FastAPI(title="Alice's Executioner")

# Enable CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/hedge")
async def hedge_endpoint(request: Request):
    """Expose the hedge tool via HTTP"""
    try:
        amount = 10.0 # Default
        
        # Try JSON body
        try:
            body = await request.json()
            if body and "amount_usd" in body:
                amount = float(body["amount_usd"])
        except Exception:
            pass
            
        # Try Query Params
        if amount == 10.0 and request.query_params.get("amount_usd"):
            amount = float(request.query_params["amount_usd"])

        print(f"✅ Processing hedge for: ${amount}")
        
        # Execute Tool
        tool = HedgeTool()
        result = await tool.execute(amount)
        
        # Return the result directly (it is now a dict, not a string)
        return result

    except Exception as e:
        print(f"❌ Error processing request: {e}")
        return {"status": "ERROR", "error": str(e)}

if __name__ == "__main__":
    print("🟢 SpoonOS Agent B Starting on Port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)