# Alice HedgeBot

Multi-agent autonomous hedging system built on Neo N3 blockchain with Docker containerization.

## 🏗️ Architecture

The system consists of two autonomous agents running in a containerized environment:

### 1. **Main Agent** (Port 8000)
- **File**: `agent.py`
- **Endpoints**: 
  - `POST /hedge` - Simulates hedge operations
  - `GET /balance/{address}` - Check NEP17 token balances
- **Features**: Neo N3 Testnet integration, wallet management, balance checking

### 2. **Oracle Agent** (Port 8001)
- **File**: `alice-hedgebot/agents/agent_oracle.py`
- **Endpoint**: `POST /market-risk`
- **Features**: Real-time market data from CoinGecko, volatility analysis, risk scoring
- **Built with**: SpoonAI SDK (`BaseTool`, `ToolCallAgent`, `ToolManager`)

## 🚀 Quick Start (Docker - Recommended)

### Prerequisites
- Docker installed and running
- Ubuntu 20.04+ (or any Linux with Docker support)

### Setup & Run

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd hedge-bot

# 2. Build the Docker image (includes Python 3.12 + SpoonAI SDK)
sudo docker build -t spoon-agent-v2 .

# 3. Run the container with both ports exposed
sudo docker run -d \
  -p 8000:8000 \
  -p 8001:8001 \
  -v $(pwd):/app \
  --name spoon-agent-v2 \
  spoon-agent-v2

sudo docker restart spoon-agent-v2 && \
sudo docker exec -d spoon-agent-v2 python3 /app/alice-hedgebot/agents/agent_oracle.py && \
sudo docker exec -d spoon-agent-v2 python3 /app/alice-hedgebot/agents/agentb.py

### Test the Agents

```bash
# Test main agent
curl http://localhost:8000/docs

# Test oracle agent - get market risk for NEO
curl -X POST http://localhost:8001/market-risk \
  -H "Content-Type: application/json" \
  -d '{"asset_symbol": "neo"}'

# Example response:
# {"timestamp":"2025-11-22T15:00:00Z","asset":"neo","current_price":4.13,"risk_level":"LOW","recommendation":"HOLD"}
```

## 📦 What's in the Container

- **Python 3.12** (slim base image)
- **SpoonAI SDK** (installed from [spoon-core](https://github.com/XSpoonAi/spoon-core))
- **Dependencies**: fastapi, uvicorn, neo-mamba, requests, pydantic
- **Build tools**: gcc, git, libssl-dev

## 🛠️ Development

### Local Development (without Docker)

**Note**: Requires Python 3.12+ and SpoonAI SDK installation.

```bash
# Install SpoonAI SDK
git clone https://github.com/XSpoonAi/spoon-core.git
cd spoon-core
pip install -r requirements.txt
pip install -e .
cd ..

# Install project dependencies
pip install -r requirements.txt

# Run agents
python3 agent.py  # Port 8000
python3 alice-hedgebot/agents/agent_oracle.py  # Port 8001
```

## 📁 Project Structure

```
hedge-bot/
├── agent.py                          # Main agent (Neo N3 interactions)
├── alice-hedgebot/
│   └── agents/
│       ├── agent_oracle.py          # Oracle agent (market risk analysis)
│       └── agentb.py                # Execution agent (on-chain hedging)
├── Dockerfile                        # Docker image with Python 3.12 + SpoonAI
├── requirements.txt                  # Python dependencies
├── .dockerignore                     # Docker build exclusions
├── .devcontainer/
│   └── devcontainer.json            # VS Code dev container config
└── README.md                         # This file
```

## 🔧 Configuration

Create a `.env` file (gitignored) with your Neo wallet credentials:

```env
NEO_WALLET_PRIVATE_KEY=your_wif_here
```

## 📚 API Documentation

- **Main Agent Swagger**: http://localhost:8000/docs
- **Main Agent ReDoc**: http://localhost:8000/redoc
- **Oracle Agent**: http://localhost:8001/market-risk

## 🌐 Neo N3 Testnet

The service connects to: `http://seed1t5.neo.org:20332`

## 🐳 Docker Commands Reference

```bash
# View running containers
sudo docker ps

# View logs
sudo docker logs spoon-agent-v2

# Stop container
sudo docker stop spoon-agent-v2

# Remove container
sudo docker rm spoon-agent-v2

# Rebuild image
sudo docker build -t spoon-agent-v2 .
```

## 📝 Notes

- Port 8000: Main agent (blockchain interactions)
- Port 8001: Oracle agent (market risk analysis)
- Code changes are synced automatically via volume mount
- SpoonAI SDK is pre-installed in the Docker image
