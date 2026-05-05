FROM python:3.14-slim

WORKDIR /app

# Copy dependency file
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy pymysql pydantic-settings \
    "pydantic[email]" python-jose bcrypt

# Copy application code
COPY app/ ./app/
COPY main.py .

# Expose port
EXPOSE 8000

# Run the application in production mode (no reload)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
