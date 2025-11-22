from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from neo3.api.noderpc import NeoRpcClient
from neo3.wallet.account import Account
from neo3.wallet.utils import script_hash_to_address
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

class HedgeRequest(BaseModel):
    amount: float

# Load WIF from environment variable
WIF = os.getenv("NEO_WALLET_PRIVATE_KEY", "[INSERT_YOUR_WIF_HERE]")
SEED_URL = "http://seed1t5.neo.org:20332"

@app.post("/hedge")
async def hedge(request: HedgeRequest):
    try:
        # Connect to Neo N3 Testnet
        async with NeoRpcClient(SEED_URL) as client:
            # Get block height
            block_height = await client.get_block_count()
            
            balance_info = "Balance check skipped (Invalid WIF)"
            wallet_address = None
            
            try:
                # Attempt to create account from WIF
                account = Account.from_wif(WIF)
                wallet_address = script_hash_to_address(account.script_hash)
                
                # Get NEP17 balances - requires address string, not script_hash
                balances_response = await client.get_nep17_balances(wallet_address)
                
                # Format balances - convert UInt160 to hex string
                balance_list = []
                for b in balances_response.balances:
                    try:
                        balance_list.append({
                            "asset_hash": "0x" + b.asset_hash.to_array()[::-1].hex(),
                            "amount": str(b.amount),
                            "last_updated_block": b.last_updated_block
                        })
                    except Exception as e:
                        print(f"Error formatting balance: {e}")
                        continue
                
                balance_info = balance_list if balance_list else "No balances found"
                
            except ValueError as e:
                # Invalid WIF format (expected for placeholder)
                balance_info = f"Invalid WIF: {str(e)}"
            except Exception as e:
                print(f"Balance check error: {e}")
                import traceback
                traceback.print_exc()
                balance_info = f"Error checking balance: {str(e)}"

            return {
                "status": "success",
                "message": "Hedge simulation executed",
                "current_block_height": block_height,
                "wallet_address": wallet_address,
                "wallet_balance": balance_info,
                "simulated_swap_amount": request.amount
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service error: {str(e)}")

@app.get("/balance/{address}")
async def get_balance(address: str):
    """
    Get NEP17 token balances for any Neo N3 address.
    No private key required - read-only operation.
    
    Example: /balance/NeMGGUng5HEZqpka2bXsWiWsuhUJ7NmzsG
    """
    try:
        # Validate address format
        from neo3.wallet.utils import is_valid_address
        if not is_valid_address(address):
            raise HTTPException(status_code=400, detail=f"Invalid Neo address: {address}")
        
        # Connect to Neo N3 Testnet
        async with NeoRpcClient(SEED_URL) as client:
            # Get block height
            block_height = await client.get_block_count()
            
            # Get NEP17 balances
            balances_response = await client.get_nep17_balances(address)
            
            # Format balances
            balance_list = []
            for b in balances_response.balances:
                try:
                    balance_list.append({
                        "asset_hash": "0x" + b.asset_hash.to_array()[::-1].hex(),
                        "amount": str(b.amount),
                        "last_updated_block": b.last_updated_block
                    })
                except Exception as e:
                    print(f"Error formatting balance: {e}")
                    continue
            
            return {
                "status": "success",
                "address": address,
                "current_block_height": block_height,
                "balances": balance_list if balance_list else [],
                "balance_count": len(balance_list)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
