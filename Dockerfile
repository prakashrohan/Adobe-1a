# Use official Python image
FROM python:3.10-slim

# Set environment variables
ENV PDF_INPUT_DIR=/app/input
ENV PDF_OUTPUT_DIR=/app/output
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install OS dependencies for pdfplumber, pytesseract, PIL, etc.
RUN apt-get update && \
    apt-get install -y \
    libpoppler-cpp-dev \
    tesseract-ocr \
    poppler-utils \
    libglib2.0-0 \
    libgl1 \
    build-essential \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Python script into the container
COPY . .

# Create input and output folders
RUN mkdir -p /app/input /app/output

# Command to run your script
CMD ["python", "main.py", "input/input.json", "output/output.json"]

