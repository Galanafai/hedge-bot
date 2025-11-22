# hedge-bot

FastAPI service that acts as a 'SpoonOS' agent for Neo N3 blockchain interactions.

## Features

- 🚀 FastAPI REST API server
- 🔗 Neo N3 Testnet integration
- 💼 Wallet management with WIF support
- 💰 NEP17 token balance checking
- 🔄 Hedge simulation endpoint

## Setup

1. **Create virtual environment and install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install fastapi uvicorn neo-mamba python-dotenv
   ```

2. **Configure environment:**
   Create a `.env` file with your Neo wallet WIF:
   ```
   NEO_WALLET_PRIVATE_KEY=your_wif_here
   ```

3. **Run the server:**
   ```bash
   uvicorn agent:app --reload --port 8000
   ```

## API Endpoints

### POST /hedge

Simulates a hedge operation and returns wallet information.

**Request:**
```json
{
  "amount": 100.0
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Hedge simulation executed",
  "current_block_height": 11315071,
  "wallet_address": "NdkNUev3JUFezNNBph7NdqC3HnfgNLLMML",
  "wallet_balance": "No balances found",
  "simulated_swap_amount": 100.0
}
```

## Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

See [TEST_SUMMARY.md](TEST_SUMMARY.md) for detailed test results.

## Files

- `agent.py` - Main FastAPI application
- `neo_wifi.py` - Utility to convert WIF to hex format
- `.env` - Environment configuration (not committed)
- `.gitignore` - Git ignore rules

## Neo N3 Testnet

The service connects to: `http://seed1t5.neo.org:20332`
