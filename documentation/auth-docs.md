# Auth Service Backend Documentation

> **Version**: 1.0.0  
> **Base URL**: `http://localhost:8000`  
> **Authentication**: JWT Bearer Token

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Models](#data-models)
4. [Authentication Flow](#authentication-flow)
5. [API Reference](#api-reference)
6. [Role-Based Access Control](#role-based-access-control)
7. [Frontend Integration Guide](#frontend-integration-guide)
8. [Error Handling](#error-handling)

---

## Overview

The Auth Service is a FastAPI-based microservice that handles:
- **User Authentication** (Registration, Login, JWT tokens)
- **Workspace Management** (Multi-tenant workspaces with unique slugs)
- **Role-Based Access Control** (Workspace-scoped permissions)
- **User & Membership Management**

### Key Concepts

| Concept | Description |
|---------|-------------|
| **User** | A registered account with email/password and optional profile data |
| **Workspace** | A multi-tenant container (e.g., a clinic or organization) |
| **WorkspaceMember** | A user's membership in a workspace with a specific role |
| **Role** | Permission level within a workspace (OWNER, ADMIN, DOCTOR) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Auth Service (FastAPI)                   │
│  ┌───────────┐  ┌────────────┐  ┌─────────────────────────┐ │
│  │ /auth/*   │  │/workspaces │  │ /users, /patients, etc  │ │
│  │ (public)  │  │ (protected)│  │ (role-protected)        │ │
│  └───────────┘  └────────────┘  └─────────────────────────┘ │
│                              │                              │
│                   ┌──────────┴──────────┐                   │
│                   │   JWT Middleware    │                   │
│                   │  + Role Dependency  │                   │
│                   └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   SQLite / PostgreSQL                       │
│   users | workspaces | workspace_members | patients | cases │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Models

### Enums

```typescript
// Global Role (stored on User)
type GlobalRole = "ADMIN" | "RADIOLOGIST";

// Workspace Role (stored on WorkspaceMember)
type WorkspaceRole = "OWNER" | "ADMIN" | "DOCTOR";

// Case Status
type CaseStatus = "PENDING" | "COMPLETED";

// Join Request Status
type RequestStatus = "PENDING" | "REJECTED" | "APPROVED";
```

### User

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` (UUID) | Auto | Unique identifier |
| `email` | `string` | ✅ | Unique email address |
| `name` | `string` | ❌ | Display name |
| `global_role` | `GlobalRole` | ❌ | Platform-wide role |
| `medical_license_id` | `string` | ❌ | Professional license |
| `avatar_url` | `string` | ❌ | Profile picture URL |
| `cnic` | `string` | ❌ | National ID (Pakistan format) |
| `phone_number` | `string` | ❌ | Contact number |
| `city` | `string` | ❌ | City |
| `gender` | `string` | ❌ | Gender |
| `terms_accepted` | `boolean` | Auto | Terms acceptance flag |
| `created_at` | `datetime` | Auto | Registration timestamp |

### Workspace

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` (UUID) | Auto | Unique identifier |
| `name` | `string` | ✅ | Workspace display name |
| `slug` | `string` | Auto | URL-friendly unique identifier (auto-generated) |
| `owner_id` | `string` | Auto | Creator's user ID |
| `created_at` | `datetime` | Auto | Creation timestamp |

### WorkspaceMember

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` (UUID) | Auto | Membership ID |
| `user_id` | `string` | ✅ | User's ID |
| `workspace_id` | `string` | ✅ | Workspace ID |
| `role` | `WorkspaceRole` | ✅ | Role in this workspace |
| `joined_at` | `datetime` | Auto | Join timestamp |

### Patient

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` (UUID) | Auto | Unique identifier |
| `workspace_id` | `string` | ✅ | Owning workspace |
| `first_name` | `string` | ✅ | First name |
| `last_name` | `string` | ✅ | Last name |
| `dob` | `datetime` | ✅ | Date of birth |
| `gender` | `string` | ✅ | Gender |
| `phone_number` | `string` | ✅ | Contact (format: +92 3xx-xxxxxxx) |
| `mrn` | `string` | ❌ | Medical Record Number |
| `cnic` | `string` | ❌ | National ID (format: xxxxx-xxxxxxx-x) |
| `address` | `string` | ❌ | Address |
| `city` | `string` | ❌ | City |

### Case

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` (UUID) | Auto | Unique identifier |
| `patient_id` | `string` | ✅ | Associated patient |
| `status` | `CaseStatus` | Auto | Default: "PENDING" |
| `priority` | `string` | Auto | Default: "normal" |
| `file_references` | `string` | ✅ | JSON string of file paths |
| `assigned_to_member_id` | `string` | ❌ | Assigned doctor (member ID) |
| `verdict` | `string` | ❌ | Doctor's diagnosis |
| `notes` | `string` | ❌ | Additional notes |

---

## Authentication Flow

### 1. Registration

```
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword123",
  "name": "John Doe",              // optional
  "global_role": "RADIOLOGIST"     // optional: "ADMIN" | "RADIOLOGIST"
}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "John Doe",
  "global_role": "RADIOLOGIST",
  "avatar_url": null,
  "created_at": "2026-02-08T00:00:00Z"
}
```

### 2. Login

```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=securepassword123
```

> ⚠️ **Note**: Uses `username` field (OAuth2 standard) but expects email.

**Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. Using the Token

Include the token in the `Authorization` header for all protected routes:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### JWT Payload Structure

```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // user_id
  "email": "user@example.com",
  "exp": 1707350400  // expiration timestamp
}
```

---

## API Reference

### Authentication Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/register` | ❌ | Register new user |
| `POST` | `/auth/login` | ❌ | Login & get JWT token |

### Workspace Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/workspaces` | ✅ | List user's workspaces |
| `POST` | `/workspaces` | ✅ | Create new workspace |
| `POST` | `/workspaces/{id}/members` | ✅ | Add member (OWNER/ADMIN only) |

---

### GET /workspaces

Get all workspaces the current user is a member of.

**Request**:
```
GET /workspaces
Authorization: Bearer <token>
```

**Response** (200 OK):
```json
[
  {
    "id": "membership-uuid",
    "workspace_id": "workspace-uuid",
    "role": "OWNER",
    "joined_at": "2026-02-08T00:00:00Z",
    "workspace_name": "My Clinic"
  }
]
```

---

### POST /workspaces

Create a new workspace. The creator automatically becomes the OWNER.

**Request**:
```
POST /workspaces
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Princeton Plainsboro Hospital"
}
```

**Response** (200 OK):
```json
{
  "id": "workspace-uuid",
  "name": "Princeton Plainsboro Hospital",
  "slug": "princeton-plainsboro-hospital",
  "owner_id": "user-uuid",
  "created_at": "2026-02-08T00:00:00Z"
}
```

> 💡 **Slug Generation**: Automatically created from the name. If duplicate exists, appends `-1`, `-2`, etc.

---

### POST /workspaces/{workspace_id}/members

Add a user to a workspace. Requires OWNER or ADMIN role.

**Request**:
```
POST /workspaces/abc123/members?email=doctor@example.com&role=DOCTOR
Authorization: Bearer <token>
```

**Query Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | `string` | ✅ | Email of user to add |
| `role` | `WorkspaceRole` | ✅ | Role to assign |

**Response** (200 OK):
```json
{
  "id": "membership-uuid",
  "workspace_id": "abc123",
  "role": "DOCTOR",
  "joined_at": "2026-02-08T00:00:00Z",
  "workspace_name": "My Clinic"
}
```

---

### Protected Example Endpoints

These demonstrate role-based access control:

| Method | Endpoint | Allowed Roles | Description |
|--------|----------|---------------|-------------|
| `POST` | `/users` | OWNER, ADMIN | Create user (placeholder) |
| `GET` | `/patients` | OWNER, ADMIN, DOCTOR | List patients (placeholder) |

**Request** (requires `X-Workspace-Id` header):
```
GET /patients
Authorization: Bearer <token>
X-Workspace-Id: workspace-uuid
```

---

## Role-Based Access Control

### How It Works

1. **Authentication**: JWT token identifies the user
2. **Workspace Context**: `X-Workspace-Id` header specifies which workspace
3. **Role Lookup**: System checks user's role in that workspace
4. **Permission Check**: Endpoint specifies which roles are allowed

### Header Requirements for Protected Routes

```
Authorization: Bearer <jwt_token>     // Required: Identifies user
X-Workspace-Id: <workspace_uuid>      // Required: Workspace context
```

### Role Hierarchy

| Role | Permissions |
|------|-------------|
| **OWNER** | Full control: manage workspace, billing, members, all data |
| **ADMIN** | Manage members, patients, cases, assignments |
| **DOCTOR** | View and analyze assigned cases, update verdicts |

### Frontend Implementation Pattern

```typescript
// Create an axios instance with workspace context
const api = axios.create({
  baseURL: 'http://localhost:8000',
});

// Add interceptor to include headers
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  const workspaceId = localStorage.getItem('current_workspace_id');
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (workspaceId) {
    config.headers['X-Workspace-Id'] = workspaceId;
  }
  return config;
});
```

---

## Frontend Integration Guide

### 1. Authentication State

```typescript
interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  currentWorkspace: Workspace | null;
  memberships: Membership[];
}
```

### 2. Recommended Auth Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as Auth Service

    U->>F: Enter email/password
    F->>A: POST /auth/login
    A-->>F: JWT Token
    F->>F: Store token in localStorage
    F->>A: GET /workspaces (with token)
    A-->>F: List of memberships
    F->>F: Store workspaces, set default
    F->>F: Redirect to dashboard
```

### 3. Workspace Switching

When user switches workspace in the UI:
1. Update `X-Workspace-Id` header value
2. Refetch workspace-specific data (patients, cases)
3. Update UI based on user's role in new workspace

### 4. Example: Login Component

```typescript
async function handleLogin(email: string, password: string) {
  // 1. Get token
  const formData = new URLSearchParams();
  formData.append('username', email);
  formData.append('password', password);
  
  const loginRes = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData,
  });
  
  const { access_token } = await loginRes.json();
  localStorage.setItem('access_token', access_token);
  
  // 2. Fetch workspaces
  const workspacesRes = await fetch('/workspaces', {
    headers: { 'Authorization': `Bearer ${access_token}` },
  });
  
  const memberships = await workspacesRes.json();
  
  // 3. Set default workspace (first one)
  if (memberships.length > 0) {
    localStorage.setItem('current_workspace_id', memberships[0].workspace_id);
  }
  
  // 4. Redirect
  router.push('/dashboard');
}
```

### 5. Role-Based UI Rendering

```tsx
function DashboardSidebar({ userRole }: { userRole: WorkspaceRole }) {
  return (
    <nav>
      <Link href="/patients">Patients</Link>
      <Link href="/cases">Cases</Link>
      
      {/* Only show for OWNER and ADMIN */}
      {['OWNER', 'ADMIN'].includes(userRole) && (
        <>
          <Link href="/members">Team Members</Link>
          <Link href="/settings">Settings</Link>
        </>
      )}
      
      {/* Only show for OWNER */}
      {userRole === 'OWNER' && (
        <Link href="/billing">Billing</Link>
      )}
    </nav>
  );
}
```

---

## Error Handling

### Standard Error Response

```json
{
  "detail": "Error message here"
}
```

### Common HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| `400` | Bad Request | Invalid input, email already registered |
| `401` | Unauthorized | Invalid/expired token, wrong credentials |
| `403` | Forbidden | Insufficient permissions for this action |
| `404` | Not Found | User/workspace/resource doesn't exist |
| `422` | Validation Error | Missing required fields, invalid format |

### Validation Error Response (422)

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "email"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

### Frontend Error Handling Pattern

```typescript
try {
  const response = await api.post('/workspaces', { name: 'New Clinic' });
  // Success handling
} catch (error) {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 401:
        // Token expired - redirect to login
        router.push('/login');
        break;
      case 403:
        // No permission
        toast.error('You do not have permission for this action');
        break;
      case 422:
        // Validation error - show field errors
        const errors = error.response.data.detail;
        setFormErrors(errors);
        break;
      default:
        toast.error(error.response?.data?.detail || 'An error occurred');
    }
  }
}
```

---

## Quick Reference Card

### Headers Cheat Sheet

| Header | Value | When to Use |
|--------|-------|-------------|
| `Content-Type` | `application/json` | POST/PUT with JSON body |
| `Content-Type` | `application/x-www-form-urlencoded` | Login endpoint |
| `Authorization` | `Bearer <token>` | All authenticated requests |
| `X-Workspace-Id` | `<workspace_uuid>` | Workspace-scoped operations |

### TypeScript Types

```typescript
interface User {
  id: string;
  email: string;
  name?: string;
  global_role?: 'ADMIN' | 'RADIOLOGIST';
  avatar_url?: string;
  created_at: string;
}

interface Workspace {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  created_at: string;
}

interface Membership {
  id: string;
  workspace_id: string;
  role: 'OWNER' | 'ADMIN' | 'DOCTOR';
  joined_at: string;
  workspace_name?: string;
}

interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
}
```
