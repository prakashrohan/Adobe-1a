# Use Python 3.11 slim base image with explicit AMD64 platform
FROM --platform=linux/amd64 python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for PDF processing
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the main application file
COPY main.py .

# Create input and output directories as expected by the challenge
RUN mkdir -p /app/input /app/output

# Set environment variables for better Python behavior
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run the application with the required directories
CMD ["python", "main.py", "--in_dir", "/app/input", "--out_dir", "/app/output"]