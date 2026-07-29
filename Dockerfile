# Use Microsoft Playwright official Python image with pre-installed Chromium and Linux dependencies
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install system dependencies & chromium driver for Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    fonts-liberation \
    libnss3 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libasound2 \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# Copy project files
COPY . .

# Expose default port (7860 for HuggingFace Spaces / 8000 for Render)
EXPOSE 7860

ENV PORT=7860
ENV HOST=0.0.0.0

# Run FastAPI app
CMD ["python", "server.py"]
