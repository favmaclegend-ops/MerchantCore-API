# Merchant Core API — API Reference

Base URL (local): `http://localhost:8000`

API Prefix: `/api/v1`

Interactive docs: Swagger UI at `/docs`, ReDoc at `/redoc`.

---

## 1. Authentication

The API issues two distinct JWT token types:

| Token | Claim `typ` | Claim `sub` | Who gets it | Used for |
|---|---|---|---|---|
| **User token** | `user` | user email | Personal users | `/api/v1/users`, `/products`, `/customers`, ... |
| **Member token** | `member` | member id (+ `org_id`) | Organisation members | `/api/v1/organisations/**` |

> Both types are sent the same way. The backend rejects a user token on org endpoints and vice versa.

### Request header

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Getting a token

- Personal: `POST /api/v1/auth/login`
- Organisation: `POST /api/v1/auth/org/login`

Tokens expire after 24 hours by default (`TOKEN_EXPIRE_MINUTES`). When expired you'll receive `401 Unauthorized` and must log in again.

### Registration flow (both account types)

1. `POST /auth/register` (or `POST /auth/org/register`) — returns a 6-digit code sent to the email (or printed to the console in dev).
2. `POST /auth/verify-email` (or `/auth/org/verify-email`) with `{ "email", "otp" }`.
3. `POST /auth/login` — now allowed.

Codes are bcrypt-hashed, expire after 15 minutes, and allow 5 wrong attempts before a resend is required.

---

## 2. Personal Account Auth (`/api/v1/auth`)

### POST /api/v1/auth/register

Registers a new user and emails a verification code.

**Request body:**
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "password": "SecurePass123."
}
```

**Response — 201 Created:**
```json
{ "message": "Registration successful. Please check your email for the verification code." }
```

**Errors:** `400` email already registered.

### POST /api/v1/auth/verify-email

Verifies the email with the 6-digit code.

**Request body:**
```json
{ "email": "user@example.com", "otp": "482913" }
```

**Response — 200 OK:**
```json
{ "message": "Email verified successfully. You can now log in." }
```

**Errors:** `404` user not found, `400` already verified / invalid / expired code, `429` too many attempts.

### POST /api/v1/auth/login

**Request body:**
```json
{ "email": "user@example.com", "password": "SecurePass123." }
```

**Response — 200 OK:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:** `401` invalid credentials, `403` email not verified or account deactivated.

### POST /api/v1/auth/resend-verification

Resends the verification code (rate-limited to once per 60s).

**Request body:**
```json
{ "email": "user@example.com", "password": "SecurePass123." }
```

**Response — 200 OK:**
```json
{ "message": "Verification code resent. Please check your inbox." }
```

**Errors:** `404` user not found, `400` already verified, `429` rate limit exceeded.

---

## 3. Organisation Auth (`/api/v1/auth/org`)

### POST /api/v1/auth/org/register

Creates an organisation, its Super Admin member, and emails a verification code. No one can log in until the organisation is verified.

**Request body:**
```json
{
  "name": "Acme Inc.",
  "business_email": "owner@acme.com",
  "username": "owner",
  "full_name": "Jane Owner",
  "password": "SecurePass123."
}
```
> `businessEmail` / `fullName` aliases are also accepted. Password must be at least 8 characters.

**Response — 201 Created:**
```json
{
  "message": "Organisation registered. Check your email for the verification code.",
  "org_id": "3f1c9d2e-..."
}
```

**Errors:** `400` missing/invalid fields, `409` email already registered.

### POST /api/v1/auth/org/verify-email

**Request body:**
```json
{ "email": "owner@acme.com", "otp": "482913" }
```
> `code` is accepted as an alias for `otp`.

**Response — 200 OK:**
```json
{ "message": "Organisation verified successfully. You can now log in." }
```

### POST /api/v1/auth/org/resend-verification

**Request body:**
```json
{ "email": "owner@acme.com" }
```

**Response — 200 OK:**
```json
{ "message": "Verification code resent. Please check your inbox." }
```

### POST /api/v1/auth/org/login

**Request body:**
```json
{ "email": "owner@acme.com", "password": "SecurePass123." }
```

**Response — 200 OK:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "member_id": "9b2e4a17-...",
  "role": "super-admin",
  "full_name": "Jane Owner",
  "username": "owner",
  "email": "owner@acme.com",
  "org_id": "3f1c9d2e-...",
  "org_name": "Acme Inc."
}
```

**Errors:** `401` invalid credentials, `403` account blocked/disabled or organisation unverified.

---

## 4. Organisation Endpoints (`/api/v1/organisations`)

All endpoints require a **member token**. Every `{org_id}` route verifies the token belongs to that org (403 otherwise).

Roles in permission errors:
- **super-admin** — everything
- **admin** — everything except ownership transfers
- **manager** (+ `hrm-manager`, `finance-manager`, `logistics-manager`) — operational management
- **staff** — reads + POS + basic record creation
- **external** — read-only

---

### 4.1 Organisation profile & settings

#### GET /api/v1/organisations
Public org info derived from the token (no `{org_id}` needed).

**Response — 200 OK:**
```json
{
  "id": "3f1c9d2e-...",
  "name": "Acme Inc.",
  "businessEmail": "owner@acme.com",
  "verified": true
}
```

#### GET /api/v1/organisations/{org_id}/settings
Requires manager+. Returns `name`, `business_email`, `member_count`.

#### PATCH /api/v1/organisations/{org_id}/settings
Requires super-admin. Updates the org name / business email.

**Request body:**
```json
{ "name": "Acme International", "business_email": "admin@acme.com" }
```
Both fields optional. **Errors:** `409` name/email already taken.

---

### 4.2 Members

| Method | Path | Requires | Description |
|---|---|---|---|
| GET | `/organisations/{org_id}/members?search=&page=` | any member | Paginated list (20/page) |
| POST | `/organisations/{org_id}/members` | manager+ | Invite a member |
| PATCH | `/organisations/{org_id}/members/{member_id}` | manager+ | Update name/email/username/phone/jobTitle |
| PATCH | `/organisations/{org_id}/members/{member_id}/role` | manager+ | Change role |
| PATCH | `/organisations/{org_id}/members/{member_id}/status` | manager+ | Toggle disabled / isActive / dataBlocked |
| GET | `/organisations/{org_id}/members/{member_id}` | any member | Member profile |
| DELETE | `/organisations/{org_id}/members/{member_id}` | super-admin | Remove member |

**POST — invite member:**
```json
{ "email": "new@acme.com", "role": "staff", "jobTitle": "Cashier" }
```
Role must be one of: `super-admin`, `admin`, `manager`, `hrm-manager`, `finance-manager`, `logistics-manager`, `staff`, `external`. An invite email is sent to the member.

**PATCH — role:**
```json
{ "role": "manager" }
```

**PATCH — status:**
```json
{ "disabled": false, "isActive": true, "dataBlocked": false }
```

**Member object (used in all responses):**
```json
{
  "id": "9b2e4a17-...",
  "name": "Jane Owner",
  "email": "owner@acme.com",
  "username": "owner",
  "phone": "+1234567890",
  "role": "super-admin",
  "jobTitle": "Owner",
  "isActive": true,
  "dataBlocked": false,
  "disabled": false
}
```

---

### 4.3 Notifications

| Method | Path | Description |
|---|---|---|
| GET | `/organisations/{org_id}/notifications?kind=&page=` | Paginated feed (30/page), `kind` filter (e.g. `sale`, `low_stock`, `credit`, `payroll`, `check_in`, `inventory`) |
| GET | `/organisations/{org_id}/notifications/unread-count` | `{ "unread": 3 }` |
| POST | `/organisations/{org_id}/notifications/{notification_id}/read` | Mark one as read (per-member state) |
| POST | `/organisations/{org_id}/notifications/read-all` | Mark all read → `{ "updated": n }` |
| DELETE | `/organisations/{org_id}/notifications/{notification_id}` | Delete one (super-admin, or admin if settings allow) |
| DELETE | `/organisations/{org_id}/notifications` | Clear all → `{ "deleted": n }` |
| GET | `/organisations/{org_id}/notification-settings` | `{ "allow_admin_delete": false }` |
| PATCH | `/organisations/{org_id}/notification-settings` | Super-admin only. `{ "allow_admin_delete": true }` |

**Notification object:**
```json
{
  "id": "7f2c...",
  "kind": "sale",
  "severity": "success",
  "is_alert": false,
  "title": "New sale completed",
  "message": "Jane Owner completed a sale of 1,250.00.",
  "amount": 1250.0,
  "ref": "txn-id",
  "actor_name": "Jane Owner",
  "actor_role": "super-admin",
  "read_by": ["9b2e4a17-..."],
  "created_at": "2026-08-08T12:00:00+00:00"
}
```

---

### 4.4 Dashboard

#### GET /api/v1/organisations/{org_id}/dashboard

**Response — 200 OK:**
```json
{
  "stats": {
    "totalRevenue": 12500.0,
    "totalSales": 42,
    "productsCount": 120,
    "customersCount": 35,
    "employeesCount": 18,
    "pendingPayroll": 2,
    "creditOutstanding": 3400.5,
    "notifications": 7
  },
  "revenueTrend": [
    { "date": "2026-07-10", "revenue": 0.0 }
  ],
  "stockLevels": [
    { "name": "Widget", "stock": 14, "threshold": 20, "status": "low-stock" }
  ]
}
```

---

### 4.5 Products & Inventory

| Method | Path | Requires | Description |
|---|---|---|---|
| GET | `/organisations/{org_id}/products?search=&category=&page=` | any member | Paginated list (50/page) |
| GET | `/organisations/{org_id}/products/status-summary` | any member | `{ "inStock", "lowStock", "outOfStock", "threshold" }` |
| POST | `/organisations/{org_id}/products` | staff+ | Create product |
| GET | `/organisations/{org_id}/products/{product_id}` | any member | Product detail |
| PATCH | `/organisations/{org_id}/products/{product_id}` | staff+ | Update product |
| DELETE | `/organisations/{org_id}/products/{product_id}` | manager+ | Delete product |

Status is **derived from stock** on every read (threshold 20): `in-stock`, `low-stock`, `out-of-stock`.

**POST / PATCH body:**
```json
{
  "name": "Widget Pro",
  "sku": "WDG-PRO-001",
  "price": 49.99,
  "stock": 150,
  "category": "Widgets",
  "image": "https://...",
  "rating": 4.5
}
```

**Product object:**
```json
{
  "id": "8aa2...",
  "name": "Widget Pro",
  "sku": "WDG-PRO-001",
  "price": 49.99,
  "stock": 150,
  "category": "Widgets",
  "status": "in-stock",
  "image": null,
  "rating": 4.5
}
```

---

### 4.6 Customers & Credit

| Method | Path | Requires | Description |
|---|---|---|---|
| GET | `/organisations/{org_id}/customers?search=&page=` | any member | Paginated list (50/page) |
| POST | `/organisations/{org_id}/customers` | staff+ | Create customer |
| GET | `/organisations/{org_id}/customers/{customer_id}` | any member | Detail |
| PATCH | `/organisations/{org_id}/customers/{customer_id}` | staff+ | Update |
| DELETE | `/organisations/{org_id}/customers/{customer_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/credit?search=` | any member | List credit entries |
| GET | `/organisations/{org_id}/credit/summary` | any member | `{ "totalOutstanding", "active", "overdue", "critical" }` |
| POST | `/organisations/{org_id}/credit/{customer_id}/purchase` | staff+ | Record a credit purchase |
| POST | `/organisations/{org_id}/credit/{customer_id}/payment` | staff+ | Record a credit payment |

**POST / PATCH customer:**
```json
{
  "name": "Acme Retail",
  "email": "buyer@acmeretail.com",
  "phone": "+123456",
  "company": "Acme Retail",
  "tier": "gold",
  "totalSpent": 1250.0,
  "creditLimit": 5000.0,
  "lastPurchase": "2026-08-01"
}
```

**Credit purchase:**
```json
{ "amount": 450.0, "code": "ACME-RET" }
```

**Credit payment:**
```json
{ "amount": 200.0 }
```

**Credit entry object:**
```json
{
  "id": "c4d3...",
  "customerId": "a1b2...",
  "customerName": "Acme Retail",
  "customerCode": "ACME-RET",
  "balance": 250.0,
  "lastPayment": "2026-08-08",
  "lastPaymentAmount": 200.0,
  "status": "active",
  "overdueDays": 0
}
```

---

### 4.7 Point of Sale & Transactions

#### POST /api/v1/organisations/{org_id}/pos/checkout
Requires staff+. Atomically decrements stock, records the transaction, and creates a `sale` notification.

**Request body:**
```json
{
  "items": [
    { "productId": "8aa2...", "quantity": 2 },
    { "productId": "7f1e...", "quantity": 1 }
  ],
  "paymentMethod": "cash",
  "customerName": "Acme Retail"
}
```
`paymentMethod` defaults to `"cash"`. `customerName` is optional and bumps the matching customer's `totalSpent`. `qty`/`product_id` are accepted as aliases.

**Response — 200 OK:** a transaction object (see below).

**Errors:** `400` empty/invalid sale, `404` product missing, `409` insufficient stock.

#### GET /api/v1/organisations/{org_id}/transactions?page=&per_page=
Paginated list (default 20/page, max 100).

#### POST /api/v1/organisations/{org_id}/transactions/{transaction_id}/refund
Requires manager+. Restores stock and marks the transaction `refunded`.

**Transaction object:**
```json
{
  "id": "e9f8...",
  "type": "sale",
  "customerName": "Acme Retail",
  "amount": 124.97,
  "status": "completed",
  "items": "2x Widget Pro, 1x Gadget",
  "lineItems": "[{\"productId\":\"...\",\"name\":\"Widget Pro\",\"sku\":\"WDG-PRO-001\",\"quantity\":2,\"unitPrice\":49.99,\"lineTotal\":99.98}]",
  "paymentMethod": "cash",
  "createdAt": "2026-08-08T12:00:00+00:00"
}
```

---

### 4.8 HRM — Employees & Benefits

| Method | Path | Requires | Description |
|---|---|---|---|
| GET | `/organisations/{org_id}/employees?department=&search=` | any member | List with departments |
| POST | `/organisations/{org_id}/employees` | manager+ | Create |
| GET | `/organisations/{org_id}/employees/{employee_id}` | any member | Detail |
| PATCH | `/organisations/{org_id}/employees/{employee_id}` | manager+ | Update |
| DELETE | `/organisations/{org_id}/employees/{employee_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/benefits` | any member | List benefits |
| POST | `/organisations/{org_id}/benefits` | manager+ | Create |
| PATCH | `/organisations/{org_id}/benefits/{benefit_id}` | manager+ | Update |
| DELETE | `/organisations/{org_id}/benefits/{benefit_id}` | manager+ | Delete |

**POST / PATCH employee:**
```json
{
  "name": "Alice Worker",
  "email": "alice@acme.com",
  "phone": "+123",
  "department": "Operations",
  "jobTitle": "Cashier",
  "employmentType": "full-time",
  "hireDate": "2026-01-15",
  "salary": 42000,
  "status": "active",
  "benefits": ["benefit-id-1"]
}
```

**Benefit body:** `{ "name": "Health Insurance", "type": "health", "cost": 250, "description": "..." }`

---

### 4.9 HRM — Payroll, Time, Attendance, Reviews

| Method | Path | Requires | Description |
|---|---|---|---|
| POST | `/organisations/{org_id}/payroll/generate` | manager+ | `{ "period": "2026-08" }` — computes gross/tax (10%)/net for all employees |
| GET | `/organisations/{org_id}/payroll?period=` | any member | List runs with `periods` |
| POST | `/organisations/{org_id}/payroll/{run_id}/paid` | manager+ | Mark run paid |
| DELETE | `/organisations/{org_id}/payroll/{run_id}` | manager+ | Delete run |
| GET | `/organisations/{org_id}/time-entries?employee_id=` | any member | List with total hours |
| POST | `/organisations/{org_id}/time-entries` | manager+ | Create |
| DELETE | `/organisations/{org_id}/time-entries/{entry_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/attendance?date=&employee_id=` | any member | List attendance |
| POST | `/organisations/{org_id}/attendance/check-in` | staff+ | `{ "employeeId": "...", "date": "2026-08-08" }` |
| GET | `/organisations/{org_id}/reviews?employee_id=` | any member | List reviews |
| POST | `/organisations/{org_id}/reviews` | manager+ | Create review |
| POST | `/organisations/{org_id}/reviews/{review_id}/complete` | manager+ | Mark completed |
| DELETE | `/organisations/{org_id}/reviews/{review_id}` | manager+ | Delete |

**Time entry body:** `{ "employeeId": "...", "date": "2026-08-08", "hours": 8, "overtimeHours": 1 }`

**Review body:** `{ "employeeId": "...", "period": "2026-08", "score": 4.2, "notes": "..." }` — `rating` auto-derived (`exceeds` ≥4.5, `meets` ≥3.5, else `below`).

**Attendance check-in response:**
```json
{
  "id": "d2f9...",
  "employeeId": "7b1a...",
  "employeeName": "Alice Worker",
  "date": "2026-08-08",
  "checkIn": "09:04",
  "status": "present"
}
```

---

### 4.10 Supply Chain

| Method | Path | Requires | Description |
|---|---|---|---|
| GET | `/organisations/{org_id}/suppliers?search=` | any member | List |
| POST | `/organisations/{org_id}/suppliers` | manager+ | Create |
| PATCH | `/organisations/{org_id}/suppliers/{supplier_id}` | manager+ | Update |
| DELETE | `/organisations/{org_id}/suppliers/{supplier_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/purchase-orders?status=` | any member | List |
| POST | `/organisations/{org_id}/purchase-orders` | manager+ | Create PO |
| POST | `/organisations/{org_id}/purchase-orders/{order_id}/receive` | manager+ | Mark received, restock |
| DELETE | `/organisations/{org_id}/purchase-orders/{order_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/shipments` | any member | List |
| POST | `/organisations/{org_id}/shipments` | manager+ | Create |
| PATCH | `/organisations/{org_id}/shipments/{shipment_id}/status` | manager+ | `{ "status": "delivered" }` |
| DELETE | `/organisations/{org_id}/shipments/{shipment_id}` | manager+ | Delete |

**Supplier body:**
```json
{
  "name": "Parts Co.",
  "contactPerson": "Bob",
  "email": "sales@partsco.com",
  "phone": "+123",
  "address": "1 Industrial Way",
  "categories": ["widgets", "hardware"],
  "paymentTerms": "Net 30",
  "status": "active"
}
```

**Purchase order body:**
```json
{
  "supplierId": "s1...",
  "items": [
    { "productId": "8aa2...", "quantity": 100, "unitPrice": 12.5 }
  ]
}
```
The PO number (`PO-YYYYMMDD-XXXX`) and totals are computed server-side.

**Shipment body:** `{ "poId": "...", "carrier": "DHL", "trackingNumber": "TRK-...", "eta": "2026-08-15", "status": "in-transit" }`

---

### 4.11 Finance

| Method | Path | Requires | Description |
|---|---|---|---|
| GET | `/organisations/{org_id}/ledger?category=` | any member | List + `income`, `expenses`, `net` |
| POST | `/organisations/{org_id}/ledger` | manager+ | Create entry |
| DELETE | `/organisations/{org_id}/ledger/{entry_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/invoices?status=` | any member | List + `paid`, `outstanding` |
| POST | `/organisations/{org_id}/invoices` | manager+ | Create |
| PATCH | `/organisations/{org_id}/invoices/{invoice_id}/status` | manager+ | `{ "status": "sent" }` |
| DELETE | `/organisations/{org_id}/invoices/{invoice_id}` | manager+ | Delete |
| GET | `/organisations/{org_id}/tax` | any member | List + `totalDue` |
| POST | `/organisations/{org_id}/tax` | manager+ | Create |
| PATCH | `/organisations/{org_id}/tax/{item_id}` | manager+ | Update |
| DELETE | `/organisations/{org_id}/tax/{item_id}` | manager+ | Delete |

**Ledger entry body:**
```json
{
  "date": "2026-08-08",
  "account": "Cash",
  "category": "income",
  "description": "Monthly rent",
  "amount": 2500,
  "reference": "INV-001",
  "status": "posted"
}
```
`category`: `income` | `expense` | `asset` | `liability`.

**Invoice body:**
```json
{
  "number": "INV-20260808-ACME",
  "customer": "Acme Retail",
  "issuedAt": "2026-08-08",
  "dueAt": "2026-09-08",
  "amount": 4500,
  "status": "draft",
  "items": [{ "description": "Widgets", "qty": 100, "unitPrice": 45 }]
}
```

**Tax item body:**
```json
{ "name": "VAT", "rate": 7.5, "basis": 100000, "period": "2026-Q3", "dueAt": "2026-09-30", "paid": 0, "status": "upcoming" }
```
`totalDue` is computed as `sum(basis * rate / 100 - paid)`.

---

## 5. Personal User Endpoints (protected)

Require a **user token** (`typ: "user"`).

### 5.1 Users

| Method | Path | Description |
|---|---|---|
| GET | `/users/me` | Current user profile |
| GET | `/users` | List all users |
| POST | `/users` | Create a user |
| GET | `/users/{user_id}` | Get user |
| PATCH | `/users/{user_id}` | Update email / password / is_active |
| DELETE | `/users/{user_id}` | Delete user |

**POST body:**
```json
{ "email": "user@example.com", "username": "johndoe", "full_name": "John Doe", "password": "SecurePass123." }
```

**PATCH body:**
```json
{ "email": "new@example.com", "password": "NewPass123.", "is_active": true }
```

**User object:**
```json
{
  "id": "3f1c9d2e-...",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "is_active": true,
  "is_verified": true,
  "created_at": "2026-08-08T10:00:00",
  "updated_at": "2026-08-08T10:00:00"
}
```

### 5.2 Products

| Method | Path | Description |
|---|---|---|
| GET | `/products` | List all |
| POST | `/products` | Create (SKU unique) |
| GET | `/products/{product_id}` | Detail |
| PATCH | `/products/{product_id}` | Update |
| DELETE | `/products/{product_id}` | Delete |

**POST body:** `{ "name": "Widget", "sku": "W-1", "price": 19.99, "stock": 50, "category": "General", "status": "in-stock" }`

Updating `stock` below 10 sets status to `low-stock` (and fires a notification); at 0 or below → `out-of-stock`.

### 5.3 Customers

| Method | Path | Description |
|---|---|---|
| GET | `/customers` | List all |
| POST | `/customers` | Create (email unique) |
| GET | `/customers/{customer_id}` | Detail |
| PATCH | `/customers/{customer_id}` | Update |
| DELETE | `/customers/{customer_id}` | Delete |

**POST body:** `{ "name": "Acme Retail", "email": "buyer@acme.com", "phone": "+123", "company": "Acme", "tier": "bronze", "total_spent": 0, "credit_limit": 0, "status": "active" }`

An `avatar` field with the customer initials is auto-generated and returned.

### 5.4 Transactions

| Method | Path | Description |
|---|---|---|
| GET | `/transactions` | List recent (last 20) |
| POST | `/transactions` | Create |

**POST body:** `{ "type": "sale", "customer_name": "Acme", "amount": 120.5, "status": "completed", "items": "2x Widget" }`

### 5.5 Credit Entries

| Method | Path | Description |
|---|---|---|
| GET | `/credit-entries` | List all |
| POST | `/credit-entries` | Create |
| PATCH | `/credit-entries/{entry_id}` | Update (a lower balance fires a payment notification) |

**POST body:** `{ "customer_id": "...", "customer_name": "Acme", "balance": 500, "status": "active" }`

### 5.6 POS Checkout

#### POST /api/v1/pos/checkout

Completes a sale, decrements product stock, records a transaction, and creates notifications.

**Request body:**
```json
{
  "items": [
    { "id": "product-id", "name": "Widget", "price": 19.99, "quantity": 2 }
  ],
  "total": 39.98,
  "payment_method": "cash"
}
```

### 5.7 Dashboard

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard/stats` | Revenue, orders, customers, stock alerts, inventory value, credit outstanding, avg ticket |
| GET | `/dashboard/revenue-trend` | Revenue per month for the last 6 months |

**`/dashboard/stats` response:**
```json
{
  "totalRevenue": 12500.5,
  "monthlyRevenue": 2100.0,
  "totalOrders": 42,
  "activeCustomers": 18,
  "lowStockAlerts": 3,
  "inventoryValue": 15000.0,
  "creditOutstanding": 3400.5,
  "avgTicket": 297.63,
  "totalProducts": 120
}
```

### 5.8 Notifications

| Method | Path | Description |
|---|---|---|
| GET | `/notifications` | List recent (last 50) |
| GET | `/notifications/unread-count` | `{ "count": 4 }` |
| PATCH | `/notifications/{notification_id}/read` | Mark as read |
| PATCH | `/notifications/read-all` | Mark all as read |
| DELETE | `/notifications/{notification_id}` | Delete |

---

## 6. System

| Method | Path | Description |
|---|---|---|
| GET | `/` | `{ "message": "Merchant Core API is running" }` |
| GET | `/health` | `{ "status": "healthy" }` |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc |

---

## 7. Examples

### curl

```bash
BASE=http://localhost:8000/api/v1

# 1. Register a personal account
curl -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","username":"johndoe","full_name":"John Doe","password":"SecurePass123."}'

# 2. Verify email (code is printed to the server console in dev)
curl -X POST "$BASE/auth/verify-email" -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","otp":"482913"}'

# 3. Login and capture the token
curl -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123."}'

# 4. Authenticated request (replace TOKEN)
curl -H "Authorization: Bearer TOKEN" "$BASE/users/me"

# 5. Register an organisation
curl -X POST "$BASE/auth/org/register" -H "Content-Type: application/json" \
  -d '{"name":"Acme Inc.","business_email":"owner@acme.com","username":"owner","full_name":"Jane Owner","password":"SecurePass123."}'

# 6. Verify + login the org, then use ORG_ID with a member token
curl -X POST "$BASE/auth/org/verify-email" -H "Content-Type: application/json" \
  -d '{"email":"owner@acme.com","otp":"482913"}'
curl -X POST "$BASE/auth/org/login" -H "Content-Type: application/json" \
  -d '{"email":"owner@acme.com","password":"SecurePass123."}'

# 7. Org-scoped request
curl -H "Authorization: Bearer MEMBER_TOKEN" \
  "$BASE/organisations/ORG_ID/products?page=1"

# 8. POS checkout for an organisation
curl -X POST "$BASE/organisations/ORG_ID/pos/checkout" \
  -H "Authorization: Bearer MEMBER_TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[{"productId":"PRODUCT_ID","quantity":1}],"paymentMethod":"card"}'
```

### JavaScript (fetch)

```javascript
const BASE = 'http://localhost:8000/api/v1';

async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  localStorage.setItem('token', data.access_token);
  return data;
}

async function api(path, options = {}) {
  const token = localStorage.getItem('token');
  return fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
}

// Use it for org-scoped calls too:
// await api(`/organisations/${orgId}/products`);
```

---

## 8. Error Handling

All errors are returned as JSON in the FastAPI format:

```json
{ "detail": "Product not found" }
```

### HTTP status codes

| Code | Meaning |
|---|---|
| 200 | OK — request successful |
| 201 | Created — resource created |
| 204 | No Content — deletion succeeded |
| 400 | Bad Request — invalid input / validation failed |
| 401 | Unauthorized — missing or invalid token |
| 403 | Forbidden — wrong role / wrong org / unverified / blocked |
| 404 | Not Found — resource doesn't exist |
| 409 | Conflict — duplicate unique value (email/SKU) or stock conflict |
| 429 | Too Many Requests — OTP attempt limit or resend rate limit |
| 500 | Internal Server Error — unexpected failure |

### Common error messages

- `"Invalid or expired token"` — bad/expired JWT.
- `"Not authorised for this organisation"` — member token used on another org's `org_id`.
- `"Insufficient permissions for this action"` — role too low for the endpoint.
- `"Email not verified..."` / `"Your organisation has not been verified..."` — login blocked until verification.
- `"Your account has been disabled. Contact your administrator."` / `"...has been blocked..."` — member deactivated/blocked.

---

## 9. Notes

- All timestamps are stored in **UTC**.
- Verification codes expire after **15 minutes**; max **5 failed attempts**.
- Resend endpoints are **rate-limited to once per 60 seconds** per email.
- Personal users and organisation members share no tables and no tokens.
- Database tables are created automatically on startup; production images also run `alembic upgrade head`.
