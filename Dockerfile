FROM python:3.14-slim

WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
COPY alembic.ini .
COPY alembic/ ./alembic/

# Install Python dependencies
RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy pymysql pydantic-settings \
    "pydantic[email]" python-jose[cryptography] bcrypt alembic cryptography resend

# Copy application code
COPY app/ ./app/
COPY main.py .

# Expose port
EXPOSE 8000

# Run migrations and start the application
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
