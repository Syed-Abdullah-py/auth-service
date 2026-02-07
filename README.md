# Auth Service

This microservice handles:
- User Registration
- Login (JWT Token Issuance)
- Password Hashing
- Token Verification

## API Endpoints
- `POST /auth/token`: Login and get access token.

## How to Run
1. Navigate to `microservices/auth-service`.
2. Create/Activate virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Run server: `uvicorn main:app --reload --port 8000`.

## Configuration
- Update `app/core/security.py` with a strong `SECRET_KEY`.
