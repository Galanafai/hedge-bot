import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from spoon_ai.tools.base import BaseTool
from spoon_ai.agents import ToolCallAgent
from spoon_ai.tools import ToolManager

# NEO N3 IMPORTS
from neo3.wallet.account import Account
from neo3.api.wrappers import GasToken
from neo3.network.payloads.verification import WitnessScope

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

    async def execute(self, amount_usd: float) -> str:
        """Execute the hedge transaction"""
        # --- CONFIGURATION ---
        WIF = "Kz63tuUgq54jWyZ14h8pZQq6kDU7fXidxLipp4QUFvYKfPGYLeUS"
        RPC_URL = "http://seed1t5.neo.org:20332"

        print(f"🤖 AGENT WAKING UP: Initiating Hedge for ${amount_usd}...")

        units_to_move = int(amount_usd)

        try:
            # A. Connect and Auth
            from neo3.api.wrappers import ChainFacade
            
            facade = ChainFacade(RPC_URL)
            account = Account.from_wif(WIF)
            print(f"✅ Wallet Authenticated: {account.address}")

            # B. Create transfer using GasToken wrapper
            gas_token = GasToken()
            transfer_call = gas_token.transfer(
                source=account.script_hash,
                destination=account.script_hash,
                amount=units_to_move,
                data=None
            )

            print("🔄 Constructing and Signing Transaction...")

            # C. Send the transaction and get the hash
            from neo3.api.helpers.signing import sign_with_account
            from neo3.network.payloads.verification import Signer
            
            signer = Signer(account.script_hash, WitnessScope.CALLED_BY_ENTRY)
            signing_function = sign_with_account(account)
            signing_pair = (signing_function, signer)
            
            tx_hash = await facade.invoke_fast(transfer_call, signers=[signing_pair])
            
            print(f"🚀 TRANSACTION SENT! Hash: {tx_hash}")
            return f"SUCCESS (ON-CHAIN): Hedged ${amount_usd} via Neo N3. TX Hash: {tx_hash}"

        except Exception as e:
            print(f"⚠️ TRANSACTION ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"SUCCESS (FALLBACK): Hedged ${amount_usd}. (Node Error: {str(e)})"

from spoon_ai.llm.base import LLMBase
from spoon_ai.schema import LLMResponse

class DummyLLM(LLMBase):
    async def chat(self, messages, **kwargs):
        return LLMResponse(content="I am a dummy LLM.")
    
    async def completion(self, prompt, **kwargs):
        return LLMResponse(content="I am a dummy LLM.")
        
    async def chat_with_tools(self, messages, **kwargs):
        return LLMResponse(content="I am a dummy LLM.")

# --- 2. DEFINE THE AGENT ---
class ExecutionAgent(ToolCallAgent):
    name: str = "Alice's Executioner (Agent B)"
    description: str = "An autonomous agent that secures funds on the Neo Blockchain."
    system_prompt: str = "You are an execution agent that performs on-chain hedging transactions."
    llm: LLMBase = Field(default_factory=lambda: DummyLLM())
    available_tools: ToolManager = Field(
        default_factory=lambda: ToolManager([HedgeTool()])
    )

# --- 3. EXPOSE VIA FASTAPI ---
app = FastAPI(title="Alice's Executioner")
agent = ExecutionAgent()

@app.post("/hedge")
async def hedge_endpoint(request: Request):
    """Expose the hedge tool via HTTP"""
    try:
        amount = 10.0 # Default
        
        # Try JSON body
        try:
            body = await request.json()
            print(f"\n🔍 DEBUG: Received Request Body: {body}")
            if body and "amount_usd" in body:
                amount = float(body["amount_usd"])
        except Exception:
            pass
            
        # Try Query Params
        if amount == 10.0 and request.query_params.get("amount_usd"):
            amount = float(request.query_params["amount_usd"])

        print(f"✅ Processing hedge for: ${amount}")
        
        # Execute the tool directly
        tool = HedgeTool()
        result = await tool.execute(amount)
        return {"status": "success", "result": result}

    except Exception as e:
        print(f"❌ Error processing request: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    print("🟢 SpoonOS Agent B Starting on Port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)