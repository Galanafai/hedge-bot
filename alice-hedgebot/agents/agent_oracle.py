from spoon_ai.tools.base import BaseTool
from spoon_ai.agents import ToolCallAgent
from spoon_ai.tools import ToolManager
from pydantic import BaseModel, Field
import requests
import os

# --- 1. Define the Data Model (The "Note" passed between agents) ---
class MarketRiskReport(BaseModel):
    timestamp: str
    asset: str
    current_price: float
    risk_level: str  # "LOW", "MEDIUM", "CRITICAL"
    recommendation: str # "HOLD" or "HEDGE_NOW"

# --- 2. Define the Tool (The Logic) ---
# This is the specific skill Agent A possesses.
def fetch_market_risk(asset_symbol: str = "neo", force_trigger: bool = False) -> MarketRiskReport:
    """
    Fetches real-time market data and calculates a 'Risk Score' 
    based on volatility (Price Drawdown & Intraday Swing).
    """
    print(f"👁️  Oracle watching: Checking {asset_symbol} price...")
    
    try:
        # Using CoinGecko Markets API for richer data (High/Low/Vol)
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": asset_symbol,
            "order": "market_cap_desc",
            "per_page": 1,
            "page": 1,
            "sparkline": "false"
        }
        response = requests.get(url, params=params).json()
        
        if not response:
            raise ValueError(f"Asset '{asset_symbol}' not found.")

        data = response[0]
        
        # Parse Data
        price = data['current_price']
        high_24h = data['high_24h']
        low_24h = data['low_24h']
        change_24h = data['price_change_percentage_24h']
        
        # --- ROBUST VOLATILITY LOGIC ---
        # 1. Drawdown from 24h High: How much has it crashed today?
        drawdown_pct = ((high_24h - price) / high_24h) * 100
        
        # 2. Intraday Volatility: Total swing range relative to current price
        volatility_pct = ((high_24h - low_24h) / price) * 100
        
        print(f"📊 Analysis for {asset_symbol.upper()}:")
        print(f"   Price: ${price}")
        print(f"   24h Change: {change_24h:.2f}%")
        print(f"   Drawdown from High: {drawdown_pct:.2f}%")
        print(f"   Intraday Volatility: {volatility_pct:.2f}%")

        risk = "LOW"
        rec = "HOLD"
        
        # DEMO MODE: Lower thresholds to always trigger hedge for demonstration
        # Logic: If we are down significantly from the top OR volatility is extreme
        if force_trigger or (drawdown_pct > 0.1) or (volatility_pct > 0.1):  # Very low thresholds for demo
            risk = "CRITICAL"
            rec = "HEDGE_NOW"
        elif (drawdown_pct > 0.005) or (volatility_pct > 0.005):
            risk = "MEDIUM"
            rec = "HEDGE_NOW"  # Changed from HOLD to HEDGE_NOW for demo
        
        from datetime import datetime, timezone
        
        return MarketRiskReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            asset=asset_symbol,
            current_price=price,
            risk_level=risk,
            recommendation=rec
        )

    except Exception as e:
        print(f"Error fetching data: {e}")
        return MarketRiskReport(
            timestamp="", asset=asset_symbol, current_price=0.0, 
            risk_level="ERROR", recommendation="HOLD"
        )


# --- 3. Define the Tool using SpoonOS SDK ---
class MarketRiskTool(BaseTool):
    name: str = "check_market_risk"
    description: str = "Fetches real-time market data and calculates risk score based on volatility"
    parameters: dict = {
        "type": "object",
        "properties": {
            "asset_symbol": {
                "type": "string",
                "description": "The cryptocurrency symbol to check (e.g., 'neo')"
            },
            "force_trigger": {
                "type": "boolean",
                "description": "Set to True to force a CRITICAL risk level (for demos)",
                "default": False
            }
        },
        "required": ["asset_symbol"]
    }
    
    async def execute(self, asset_symbol: str = "neo", force_trigger: bool = False) -> dict:
        """Execute the market risk check"""
        report = fetch_market_risk(asset_symbol, force_trigger)
        return report.model_dump()

# --- 4. Define the Agent using SpoonOS SDK ---
class OracleAgent(ToolCallAgent):
    name: str = "The Watchtower"
    description: str = "Monitors market volatility and signals when to hedge"
    system_prompt: str = "You are an oracle agent that monitors cryptocurrency markets and alerts when hedging is needed."
    max_steps: int = 5
    available_tools: ToolManager = Field(
        default_factory=lambda: ToolManager([MarketRiskTool()])
    )
    
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="The Watchtower")

# Add CORS middleware to allow browser requests
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for demo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RiskRequest(BaseModel):
    asset_symbol: str = "neo"

from fastapi import Request

@app.post("/market-risk")
async def check_market_risk(request: Request):
    """Expose the market risk tool via HTTP"""
    try:
        symbol = "neo" # Default
        
        # 1. Try to get JSON body
        try:
            body = await request.json()
            print(f"\n🔍 DEBUG: Received Request Body: {body}")
            if body and "asset_symbol" in body:
                symbol = body["asset_symbol"]
        except Exception:
            pass
            
        # 2. If not in body, check query params
        if symbol == "neo" and request.query_params.get("asset_symbol"):
            print(f"\n🔍 DEBUG: Received Query Params: {request.query_params}")
            symbol = request.query_params["asset_symbol"]

        print(f"✅ Processing request for: {symbol}")
        return fetch_market_risk(symbol)

    except Exception as e:
        print(f"❌ Error parsing request: {e}")
        return {"error": str(e)}

# To run the agent and expose the API:
if __name__ == "__main__":
    # Start the HTTP server so n8n can call it
    uvicorn.run(app, host="0.0.0.0", port=8001)