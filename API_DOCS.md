# Merchant Core API Documentation

Base URL: `https://merchantcore-api.onrender.com`

API Prefix: `/api/v1`

---

## Authentication

This API uses JWT (JSON Web Tokens) for authentication. Most endpoints require a valid Bearer token in the Authorization header.

### Headers for Authenticated Requests

```
Authorization: Bearer <your-jwt-token>
Content-Type: application/json
```

---

## Endpoints

### 1. Register a New User

**POST** `/api/v1/auth/register`

Registers a new user and sends a verification email.

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "password": "SecurePass123."
}
```

**Field Descriptions:**
- `email` - Valid email address (must be unique)
- `username` - Unique username identifier
- `full_name` - User's full display name

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character

**Response (201 Created):**
```json
{
  "message": "Registration successful. Please check your email to verify your account."
}
```

**Error Responses:**
- `400 Bad Request` - Email already registered
- `500 Internal Server Error` - Failed to send verification email

---

### 2. Verify Email

**POST** `/api/v1/auth/verify-email`

Verifies user's email using the token sent to their inbox.

**Request Body:**
```json
{
  "token": "your-verification-token"
}
```

**Response (200 OK):**
```json
{
  "message": "Email verified successfully. You can now log in."
}
```

**Alternative: GET Request**
```
GET /api/v1/auth/verify-email?token=your-verification-token
```

**Error Responses:**
- `400 Bad Request` - Invalid or expired token
- `400 Bad Request` - Email already verified
- `404 Not Found` - User not found

---

### 3. Login

**POST** `/api/v1/auth/login`

Authenticates a user and returns a JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid email or password
- `403 Forbidden` - Email not verified
- `403 Forbidden` - Account is deactivated

---

### 4. Resend Verification Email

**POST** `/api/v1/auth/resend-verification`

Resends the verification email if the user didn't receive it.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123."
}
```

**Response (200 OK):**
```json
{
  "message": "Verification email resent. Please check your inbox."
}
```

**Error Responses:**
- `404 Not Found` - User not found
- `400 Bad Request` - Email already verified
- `429 Too Many Requests` - Rate limit exceeded

---

### 5. Get Current User Profile

**GET** `/api/v1/users/me`

Returns the authenticated user's profile.

**Headers:**
```
Authorization: Bearer <your-jwt-token>
```

**Response (200 OK):**
```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "is_active": true,
  "is_verified": true,
  "created_at": "2026-05-05T22:00:00",
  "updated_at": "2026-05-05T22:00:00"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or expired token

---

## Example Usage

### Using Fetch (JavaScript/TypeScript)

```javascript
const API_BASE = 'https://merchantcore-api.onrender.com/api/v1';

// Register
async function register(email, username, full_name, password) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, username, full_name, password }),
  });
  return response.json();
}

// Login
async function login(email, password) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json();
  
  if (response.ok) {
    // Store the token
    localStorage.setItem('token', data.access_token);
  }
  
  return data;
}

// Get current user profile (authenticated request)
async function getProfile() {
  const token = localStorage.getItem('token');
  
  const response = await fetch(`${API_BASE}/users/me`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });
  
  return response.json();
}

// Verify email
async function verifyEmail(token) {
  const response = await fetch(`${API_BASE}/auth/verify-email`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ token }),
  });
  return response.json();
}
```

### Using Axios (JavaScript/TypeScript)

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'https://merchantcore-api.onrender.com/api/v1',
});

// Register
async function register(email, username, full_name, password) {
  return api.post('/auth/register', { email, username, full_name, password });
}

// Login
async function login(email, password) {
  const response = await api.post('/auth/login', { email, password });
  localStorage.setItem('token', response.data.access_token);
  return response;
}

// Set auth header for subsequent requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Get profile
async function getProfile() {
  return api.get('/users/me');
}
```

### Using curl (Command Line)

```bash
# Register
curl -X POST "https://merchantcore-api.onrender.com/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "username": "johndoe", "full_name": "John Doe", "password": "SecurePass123."}'

# Login
curl -X POST "https://merchantcore-api.onrender.com/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "SecurePass123."}'

# Get profile (replace TOKEN with actual token)
curl -H "Authorization: Bearer TOKEN" \
  "https://merchantcore-api.onrender.com/api/v1/users/me"

# Verify email
curl -X POST "https://merchantcore-api.onrender.com/api/v1/auth/verify-email" \
  -H "Content-Type: application/json" \
  -d '{"token": "YOUR_VERIFICATION_TOKEN"}'
```

---

## Token Expiration

JWT tokens expire after 30 minutes (configurable). When the token expires, you'll receive a `401 Unauthorized` response. You'll need to log in again to get a new token.

---

## Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request successful |
| 201 | Created - Resource created successfully |
| 400 | Bad Request - Invalid input or parameters |
| 401 | Unauthorized - Invalid or missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Server error |

---

## Notes

- Email verification is required before logging in
- Passwords are securely hashed using bcrypt
- Rate limiting is applied to verification email resends
- All timestamps are in UTC
- Token expiration can be configured via `TOKEN_EXPIRE_MINUTES` environment variable
