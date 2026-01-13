# API Gateway Notes
- Staging endpoint: https://api-staging.internal.lab
- Auth: Bearer token (get from auth service)
- Rate limit: 100 req/min per IP

## Common Errors
- 401 Unauthorized: Check if token is expired (refresh via /auth/refresh)
- 502 Bad Gateway: Usually means backend service is restarting
