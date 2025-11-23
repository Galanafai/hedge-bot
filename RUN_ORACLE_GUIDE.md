# Running agent_oracle.py

## Current Status

✅ **spoon_ai module is installed** in the existing Docker container  
✅ **agent_oracle.py has been modified** to run on port 8001  
⚠️ **Port 8001 is not exposed** in the current container

## Quick Start (Recommended)

Since the current container has permission issues and doesn't expose port 8001, here's the simplest way to run agent_oracle.py:

### Option 1: Run agent_oracle.py directly in the existing container (port 8001 won't be accessible from host)

```bash
# Execute agent_oracle.py inside the container (runs on port 8001 internally)
sudo docker exec -d spoon-agent-container python3 /app/alice-hedgebot/agents/agent_oracle.py

# Test from inside the container
sudo docker exec spoon-agent-container curl http://localhost:8001/market-risk
```

### Option 2: Rebuild and create a new container with both ports exposed

```bash
# 1. Update Dockerfile to expose port 8001 (already done)

# 2. Rebuild the image with spoon_ai pre-installed
sudo docker build -t spoon-agent-v2 -f- . <<EOF
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential gcc libssl-dev git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
RUN git clone https://github.com/XSpoonAi/spoon-core.git /tmp/spoon-core && \
    pip install -r /tmp/spoon-core/requirements.txt && \
    pip install -e /tmp/spoon-core
COPY . .
EXPOSE 8000 8001
CMD ["tail", "-f", "/dev/null"]
EOF

# 3. Force remove the old container (if permission issues persist, reboot may be needed)
sudo docker rm -f spoon-agent-container || true

# 4. Run new container with both ports
sudo docker run -d -p 8000:8000 -p 8001:8001 -v $(pwd):/app --name spoon-agent-v2 spoon-agent-v2

# 5. Run agent.py on port 8000
sudo docker exec -d spoon-agent-v2 python3 /app/agent.py

# 6. Run agent_oracle.py on port 8001
sudo docker exec -d spoon-agent-v2 python3 /app/alice-hedgebot/agents/agent_oracle.py
```

### Option 3: Test agent_oracle.py without Docker

If you just want to test the functionality:

```bash
# The spoon_ai module is only in the container, so this won't work on the host
# But you can test the market risk logic directly
python3 alice-hedgebot/agents/agent_oracle.py
```

## Testing the Agent

Once running, test the agent:

```bash
# Test agent_oracle.py (port 8001)
curl http://localhost:8001/market-risk

# With parameters
curl -X POST http://localhost:8001/market-risk \
  -H "Content-Type: application/json" \
  -d '{"asset_symbol": "bitcoin"}'
```

## Notes

- The current container (`spoon-agent-container`) has permission issues preventing it from being stopped
- Port 8001 is not exposed in the current container, so you can't access it from the host
- The simplest solution is to rebuild with a new Dockerfile that includes spoon_ai and exposes both ports
