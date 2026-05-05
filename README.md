# Merchant Core API

A robust merchant management API service built with FastAPI and SQLAlchemy.

## Features

- User registration and authentication
- Email verification with SMTP support
- User management (CRUD operations)
- JWT-based authentication
- Rate limiting for email verification
- SQLite database (easily configurable to PostgreSQL/MySQL)

## Tech Stack

- **Framework**: FastAPI
- **ORM**: SQLAlchemy
- **Database**: SQLite (default)
- **Authentication**: JWT (JSON Web Tokens)
- **Email**: SMTP with TLS support
- **Validation**: Pydantic v2

## Prerequisites

- Python 3.8+
- pip or uv package manager

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd merchant-core-api
```

2. Install dependencies:
```bash
uv sync
```
Or with pip:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Update the values in `.env` with your configuration

```bash
cp .env.example .env
```

4. Run the application:
```bash
uv run fastapi dev main.py
```

The API will be available at `http://localhost:8000`

## Configuration

Create a `.env` file with the following variables:

```env
# Application
SECRET_KEY=your-secret-key-here
DEBUG=false

# Database
DATABASE_URL=sqlite:///./app.db

# JWT
ACCESS_TOKEN_EXPIRE_MINUTES=30
TOKEN_EXPIRE_MINUTES=30

# SMTP Configuration (for email verification)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME="Merchant Core API"
```

### Gmail SMTP Setup

To use Gmail SMTP:
1. Enable 2-Step Verification on your Google Account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the generated password in `SMTP_PASSWORD`

## API Documentation

Once the server is running, access the interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /register` - Register a new user
- `POST /login` - Login and get access token
- `GET /verify-email?token=` - Verify email via link
- `POST /verify-email` - Verify email with token
- `POST /resend-verification` - Resend verification email

### Users (`/api/v1/users`)
- `GET /` - List all users
- `POST /` - Create a new user
- `GET /{user_id}` - Get user details
- `PATCH /{user_id}` - Update user
- `DELETE /{user_id}` - Delete user

### Health Check
- `GET /health` - Check API health status

## Development

### Running in development mode:
```bash
uv run fastapi dev main.py
```

### Database Management

The application uses SQLite by default. The database file (`app.db`) is created automatically.

To clear the database:
```bash
python3 -c "import sqlite3; conn = sqlite3.connect('app.db'); conn.execute('DELETE FROM users'); conn.commit(); conn.close()"
```

## Project Structure

```
merchant-core-api/
├── app/
│   ├── core/          # Security and utility functions
│   ├── db/            # Database configuration
│   ├── models/        # SQLAlchemy models
│   ├── routers/       # API route handlers
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic services
│   └── config.py      # Application settings
├── main.py            # Application entry point
├── .env               # Environment variables (not tracked)
├── .env.example       # Environment variables template
└── README.md          # This file
```

## License

[Add your license here]

## Contact

[Add contact information here]
