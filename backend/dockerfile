# ─── Stage 1: Builder ───────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
# Install packages into a prefix directory
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
RUN mkdir -p /app/data


# ─── Stage 2: Final (Distroless) ────────────────────────────────────────────
FROM gcr.io/distroless/python3-debian12

# Use built-in nonroot user
USER nonroot

WORKDIR /app

# Copy the entire install tree to the non-root user's local directory
COPY --from=builder --chown=nonroot:nonroot /install /home/nonroot/.local

# Copy database directory from builder with correct ownership
COPY --from=builder --chown=nonroot:nonroot /app/data /app/data

# Copy application source code
COPY --chown=nonroot:nonroot . .

# Set paths so Python and Shell can locate installed packages and binaries
ENV PATH="/home/nonroot/.local/bin:$PATH"
ENV PYTHONPATH="/home/nonroot/.local/lib/python3.11/site-packages"

EXPOSE 8000

# Run FastAPI app using python module syntax
ENTRYPOINT ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
