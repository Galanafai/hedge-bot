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
        
        # Logic: If we are down significantly from the top OR volatility is extreme
        if force_trigger or (drawdown_pct > 5.0) or (volatility_pct > 8.0):
            risk = "CRITICAL"
            rec = "HEDGE_NOW"
        elif (drawdown_pct > 3.0) or (volatility_pct > 5.0):
            risk = "MEDIUM"
            rec = "HOLD" # Watch closely
            
        return MarketRiskReport(
            timestamp="2025-11-22T15:00:00Z", # In prod, use datetime.now()
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

# For testing directly via CLI
if __name__ == "__main__":
    report = fetch_market_risk("neo")
    print(f"\n📋 REPORT GENERATED:\n{report.model_dump_json(indent=2)}")