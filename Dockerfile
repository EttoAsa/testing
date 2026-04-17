FROM python:3.10.16-slim

# Build argument for architecture (amd64 or arm64)
ARG TARGETARCH=amd64

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    nodejs \
    npm \
    libreoffice \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Install Prettier globally
RUN npm install -g prettier

# Install Pandoc 3.7.0.2 based on architecture
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        wget https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-1-arm64.deb \
        && dpkg -i pandoc-3.7.0.2-1-arm64.deb \
        && rm pandoc-3.7.0.2-1-arm64.deb; \
    else \
        wget https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-1-amd64.deb \
        && dpkg -i pandoc-3.7.0.2-1-amd64.deb \
        && rm pandoc-3.7.0.2-1-amd64.deb; \
    fi

# Set working directory
WORKDIR /app

# Copy requirements.txt first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create GENERATED_FILES directory
RUN mkdir -p /app/GENERATED_FILES
RUN mkdir -p /data/sources

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

RUN git config --system --add safe.directory "*"

USER appuser

# Declare volume mount point
VOLUME /app
VOLUME /data/sources

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default entrypoint
ENTRYPOINT ["python"]
CMD ["convert.py"]