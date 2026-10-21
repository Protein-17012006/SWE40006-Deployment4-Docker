# syntax=docker/dockerfile:1
# Docker "Get Started" friendlyhello, modernised (SWE40006 Task 4.2).

# Use an official Python runtime as a parent image
FROM python:3.14-slim

ARG APP_VERSION=1.0.0
LABEL org.opencontainers.image.title="friendlyhello" \
      org.opencontainers.image.description="Hello-world web server (Flask + Redis visit counter) - SWE40006 Task 4.2" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Protein-17012006/SWE40006-Deployment4-Docker"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set the working directory to /app
WORKDIR /app

# Install the packages listed in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application into the container
COPY app.py .

# Run as an unprivileged user; Docker still lets it bind port 80 inside the container
RUN useradd --create-home --uid 10001 app
USER 10001

# Make port 80 available to the world outside this container
EXPOSE 80

# Define environment variable
ENV NAME=World

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1/healthz', timeout=2)"]

# Serve app.py with gunicorn when the container launches
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "2", "--access-logfile", "-", "app:app"]
