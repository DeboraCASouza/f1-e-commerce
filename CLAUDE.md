# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Academic assignment (3 pts, individual): a minimal distributed e-commerce system built with microservices, data replication, heartbeat-based fault detection, and JWT authentication. No code exists yet — only `requisitos.md` with the full specification.

## Required Delivery Structure

```
entrega/
├── gateway/           # API Gateway
├── users/             # Users microservice
├── products/          # Products microservice (with 2 replicas)
├── orders/            # Orders microservice
├── docker-compose.yml # optional (+0.2 pt bonus)
├── README_execucao.md # mandatory: step-by-step run instructions
└── relatorio.pdf      # 1-2 pages answering 5 architectural questions
```

## Architecture

```
Client (curl / Postman)
        │
┌───────▼────────┐
│  API Gateway   │  ← single entry point, runs heartbeat checks
└──┬──────┬──────┬┘
   │      │      │
:5001  :5002  :5003
Users  Prods  Orders
       :5012 (replica)
```

Each service has its own data store (JSON file or SQLite). No shared in-memory state between services.

## Services and Endpoints

### Users (port 5001)
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/users/register` | — | name, email, hashed password |
| POST | `/users/login` | — | returns JWT |
| GET | `/users/:id` | JWT | user profile |

### Products (port 5002 + replica 5012)
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/products` | — | round-robin across replicas |
| GET | `/products/:id` | — | round-robin across replicas |
| POST | `/products` | JWT (admin role) | propagated to both replicas before confirming |

### Orders (port 5003)
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/orders` | JWT | links userId + productId |
| GET | `/orders/:userId` | JWT | user's order list |

### Health (all services)
| Method | Path | Response |
|--------|------|----------|
| GET | `/health` | `{ "status": "ok" }` |

## Key Implementation Requirements

### Replication (Products)
- Writes must be propagated to **both** replicas before returning success to the client (strong consistency approach is simplest).
- Reads distributed via round-robin between port 5002 and 5012.
- Document the consistency strategy chosen in the report.

### Heartbeat (Gateway)
- Every 5 seconds, gateway sends `GET /health` to each service.
- If a service fails 2 consecutive attempts: log with timestamp, return `503 Service Unavailable` for requests to that service.
- When the service recovers, log the recovery.

### JWT
- Generated at login; payload must include: `userId`, `email`, `role` (`user` or `admin`), `exp`.
- Store the JWT secret in an environment variable.
- Gateway forwards the JWT header to downstream services.
- Protected endpoints return `401` for missing/invalid token, `403` for insufficient role.
- Passwords stored as bcrypt or SHA-256 hash.

## Technology Choice

Any language or framework is allowed. Suggested: Node.js + Express, Python + Flask/FastAPI, or Go. Inter-service communication must be HTTP/REST at minimum.

## Penalties to Avoid
- System fails to start: −1.0 pt
- Missing or insufficient `README_execucao.md`: −0.3 pt
- Late submission: −0.3 pt/day (max −1.0 pt)

## Report Questions (must answer in relatorio.pdf)
1. How was inter-service communication implemented? (REST, gRPC, queue, etc.)
2. What consistency strategy was used for replication? Strong or eventual? Why?
3. What happens if the Orders service goes down? Does the rest keep working?
4. How does JWT prevent a regular user from creating products?
5. What limitations does this implementation have compared to a real production system?
