# Use the official lightweight Python 3.12 image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies including git for cloning spoon-core
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libssl-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy your requirements file first (for caching speed)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install spoon_ai from GitHub
RUN git clone https://github.com/XSpoonAi/spoon-core.git /tmp/spoon-core && \
    pip install --no-cache-dir -r /tmp/spoon-core/requirements.txt && \
    pip install --no-cache-dir -e /tmp/spoon-core

# Copy the rest of your application code
COPY . .

# Expose the ports for both agents
EXPOSE 8000 8001

# Command to keep container running (we'll exec into it to run agents)
CMD ["tail", "-f", "/dev/null"]