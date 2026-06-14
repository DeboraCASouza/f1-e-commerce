# Mini E-commerce Distribuído

Sistema de e-commerce baseado em microsserviços com replicação de dados, detecção de falhas por heartbeat e autenticação JWT.

## Arquitetura

```
Cliente
   │
   ▼
API Gateway (:8000)  ←  heartbeat a cada 5s
   ├── Usuários    (:5001)
   ├── Produtos R1 (:5002)  ┐  réplicas com
   ├── Produtos R2 (:5012)  ┘  consistência forte
   └── Pedidos     (:5003)
```

## Tecnologias

- **Python 3.11** + **FastAPI** + **uvicorn**
- **SQLite** — banco de dados por serviço
- **JWT (HS256)** — autenticação e autorização
- **bcrypt** — hash de senhas
- **Docker + Docker Compose** — orquestração
- **TLS/HTTPS** — certificado auto-assinado gerado no boot

## Subir o projeto

```bash
docker-compose up --build
```

Na primeira execução o gateway gera automaticamente um certificado TLS. Acesse:

- **Dashboard:** https://localhost:8000/ui
- **API docs:** https://localhost:8000/docs

> O browser vai exibir aviso de certificado auto-assinado — clique em **Avançado → Prosseguir**.

## Endpoints principais

| Serviço | Método | Rota | Auth |
|---------|--------|------|------|
| Usuários | POST | `/users/register` | — |
| Usuários | POST | `/users/login` | — |
| Usuários | GET | `/users/:id` | JWT |
| Produtos | GET | `/products` | — |
| Produtos | POST | `/products` | JWT admin |
| Pedidos | POST | `/orders` | JWT |
| Pedidos | GET | `/orders/:userId` | JWT |
| Gateway | GET | `/health` | — |

## Estrutura

```
entrega/
├── gateway/      # API Gateway + heartbeat + proxy
├── users/        # Cadastro, login, JWT
├── products/     # Catálogo (2 réplicas)
├── orders/       # Pedidos + controle de estoque
├── frontend/     # Dashboard HTML
├── docker-compose.yml
├── README_execucao.md
└── relatorio.pdf
```
