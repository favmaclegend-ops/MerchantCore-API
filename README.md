# Merchant Core API

A multi-tenant merchant management API service built with FastAPI and SQLAlchemy. It powers everything a modern merchant needs: point-of-sale, inventory, customers & credit, HR & payroll, supply chain, and finance — all behind one JSON API.

## Features

### Accounts & Authentication
- **Two account types** on a single backend:
  - **Personal users** (`/api/v1/auth`) — single-owner account with `typ: "user"` tokens.
  - **Organisations** (`/api/v1/auth/org`) — multi-member workspaces with `typ: "member"` tokens.
- Email verification via **6-digit OTP codes** (bcrypt-hashed, 15-minute expiry, 5 attempts max).
- JWT-based authentication with a configurable expiry (default 24h).
- Rate-limited verification resends (60s cooldown).
- Passwords hashed with bcrypt.

### Organisation Workspace (multi-tenant)
Every organisation endpoint is scoped by `org_id` — cross-tenant access is structurally impossible.

- **Role-based permissions**: `super-admin`, `admin`, `manager` (+ `hrm-manager`, `finance-manager`, `logistics-manager`), `staff`, `external`.
- **Member management** — invite, edit profiles, change roles, enable/disable/block.
- **Notification feed** — per-member read state, alert severity, settings.
- **Modules**:
  - Point of Sale (checkout, transactions, refunds)
  - Inventory (products, low-stock alerts, status summary)
  - Customers & Credit (credit purchases, payments, outstanding balances)
  - HRM (employees, benefits, payroll runs, time entries, attendance, reviews)
  - Supply chain (suppliers, purchase orders, shipments)
  - Finance (ledger, invoices, tax items)
  - Dashboard (revenue, sales, stock levels, credit)

### Personal Workspace (single-owner)
- User profile & management CRUD.
- Products, customers, transactions, credit entries, POS checkout.
- Dashboard stats and revenue trend.
- Global notification feed.

## Tech Stack

- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2.x
- **Database**: SQLite (default) or MySQL / PostgreSQL
- **Authentication**: JWT (python-jose) + bcrypt
- **Email**: Resend (with dev fallback that prints codes to the console)
- **Validation**: Pydantic v2
- **Caching**: cachetools TTL caches
- **Migrations**: Alembic
- **Linting**: Ruff

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- MySQL 8.0 (optional, for production; `docker-compose up -d db`)

## Installation

1. Clone the repository and enter the directory:
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
pip install -e ".[dev]"
```

3. Configure environment variables:
```bash
cp .env.example .env
```

4. Run the application:
```bash
uv run fastapi dev main.py
```

The API will be available at `http://localhost:8000`.

## Configuration

Create a `.env` file from `.env.example`:

```env
# Application
SECRET_KEY=your-secret-key-here
DEBUG=false
ALLOWED_HOSTS=["*"]

# Database (SQLite by default; MySQL for production)
DATABASE_URL=sqlite:///./app.db
# DATABASE_URL=mysql+pymysql://root@localhost:3306/merchant_core

# Tokens (minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=1440
TOKEN_EXPIRE_MINUTES=1440

# Email (Resend) — leave RESEND_API_KEY empty in dev to print codes to console
RESEND_API_KEY=
SMTP_FROM_EMAIL=onboarding@resend.dev
SMTP_FROM_NAME="Merchant Core API"

# Public URLs
PUBLIC_URL=
FRONTEND_URL=http://localhost:5173
```

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT signing secret — change in production | `change-me-in-production` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./app.db` |
| `TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes | `1440` (24h) |
| `RESEND_API_KEY` | Resend API key for transactional email | empty (dev mode) |
| `ALLOWED_HOSTS` | CORS allowed origins | `["*"]` |
| `FRONTEND_URL` | Frontend origin used in invite links | `http://localhost:5173` |

### Email verification in development

Without a `RESEND_API_KEY`, the verification code is **printed to the server console** instead of being emailed, so you can test the verify flow locally:

```
[dev-email] To: you@example.com | Subject: Your Verification Code
```

## Running with Docker

Start the MySQL database and API together:

```bash
cp .env.example .env
docker-compose up --build
```

The API runs at `http://localhost:8000`, MySQL on port `3306`.

## Database

Tables are created automatically on startup (`Base.metadata.create_all`). Alembic migrations live in `alembic/` and run before boot in the Docker image:

```bash
alembic upgrade head
```

## API Documentation

Once the server is running, interactive docs are available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

Full endpoint reference with request/response examples: **[API.md](API.md)**

## Project Structure

```
merchant-core-api/
├── app/
│   ├── core/          # Security (JWT/OTP), permissions, TTL caches
│   ├── db/            # Database engine and session
│   ├── models/        # SQLAlchemy models (user, org + all org modules)
│   ├── routers/       # API route handlers
│   ├── schemas/       # Pydantic request/response models
│   └── services/      # Business logic (org UI/admin/user, email, rate limiting)
├── alembic/           # Database migrations
├── tests/             # pytest suite
├── postman/           # Postman collection & environment
├── main.py            # Application entry point
├── docker-compose.yml # Local MySQL + API
├── Dockerfile         # Production image
└── .env.example       # Environment variables template
```

## Testing

```bash
uv run pytest
```

## License

MIT
