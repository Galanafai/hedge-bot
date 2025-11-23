# Git Commit Guide

## Files to Commit to GitHub

### ✅ Core Application Files
```
agent.py
alice-hedgebot/agents/agent_oracle.py
alice-hedgebot/agents/agentb.py
alice-hedgebot/main.py
test_trigger.py
create_wallet.py
neo_wifi.py
```

### ✅ Docker Configuration
```
Dockerfile
requirements.txt
.dockerignore
.devcontainer/devcontainer.json
```

### ✅ Documentation
```
README.md
TEST_SUMMARY.md
RUN_ORACLE_GUIDE.md (optional - helpful for users)
```

### ✅ Git Configuration
```
.gitignore
```

## ❌ Files to EXCLUDE (Already in .gitignore)

```
.env                    # Contains private keys - NEVER commit
.venv/                  # Virtual environment
venv/                   # Virtual environment
__pycache__/            # Python cache
*.pyc                   # Compiled Python
.git/                   # Git metadata
alice_balance.txt       # Runtime data
```

## 📝 Recommended Commit Commands

```bash
# Check current branch
git branch

# Switch to main branch (or create a new feature branch)
git checkout main
# OR create a new branch for this feature
git checkout -b docker-containerization

# Add the files
git add Dockerfile
git add requirements.txt
git add .dockerignore
git add .devcontainer/
git add README.md
git add alice-hedgebot/agents/agent_oracle.py
git add agent.py

# Check what will be committed
git status

# Commit with a descriptive message
git commit -m "Add Docker containerization with Python 3.12 and SpoonAI SDK

- Added Dockerfile with Python 3.12 and SpoonAI SDK pre-installed
- Updated requirements.txt with project dependencies
- Added .dockerignore for efficient builds
- Added .devcontainer for VS Code development
- Updated README.md with Docker setup instructions
- Modified agent_oracle.py to run on port 8001
- Both agents now run in isolated container environment"

# Push to GitHub
git push origin main
# OR if you created a feature branch
git push origin docker-containerization
```

## 🔍 Verify Before Pushing

```bash
# Make sure .env is NOT staged
git status | grep .env
# Should return nothing

# View what will be committed
git diff --cached

# List all tracked files
git ls-files
```

## 🌿 Branch Strategy

Current branches:
- `main` - Production/stable code
- `gui` - GUI-related features (currently active)
- `agentB` - Agent B development

**Recommendation**: 
- Create a new branch `docker-setup` or merge into `main`
- Keep sensitive data (`.env`, private keys) out of all branches

## 📦 Optional: Create .env.example

Create a template for other developers:

```bash
# Create .env.example (safe to commit)
cat > .env.example << 'EOF'
# Neo N3 Wallet Configuration
NEO_WALLET_PRIVATE_KEY=your_wif_key_here

# Optional: API Keys
# COINGECKO_API_KEY=your_api_key_here
EOF

git add .env.example
```
