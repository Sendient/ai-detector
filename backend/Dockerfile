# Use an official Python runtime as a parent image
# Updated to Python 3.13 slim-bookworm based on your preferences
FROM python:3.13-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Prevent python from writing pyc files to disc
# and prevent buffering stdout and stderr.
# Use KEY=VALUE format for ENV instructions.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# PIP environment variables for better control.
# Comment is on a separate line to avoid parsing issues.
ENV PIP_NO_CACHE_DIR=off
# Disables pip cache (can be 'on' to speed up subsequent builds if requirements don't change often)
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV PIP_DEFAULT_TIMEOUT=100

# Install system dependencies if needed (e.g., for libraries that require compilation)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install pip requirements
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
# It's good practice to upgrade pip first.
# Using --no-cache-dir for installs to keep image size smaller.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This assumes your FastAPI app code (including main.py) is in an 'app' subdirectory
# within your build context (e.g., ./backend/app/ -> /app/app/ in container)
COPY ./app /app/app

# Expose the port the app runs on (uvicorn default is 8000, matching your app)
EXPOSE 8000

# Command to run the application using uvicorn
# Starts the server on 0.0.0.0 to be accessible from outside the container
# Assumes your FastAPI app instance is named 'app' in 'app/main.py' (relative to WORKDIR /app)
# So, the path is app.main:app because of the COPY ./app /app/app structure.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug", "--access-log", "--proxy-headers", "--forwarded-allow-ips='*'"]

# For a production-ready setup, you might consider more Uvicorn workers:
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
# The number of workers depends on your app's nature and available resources.
