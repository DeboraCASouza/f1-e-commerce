# README de Execução — Mini E-commerce Distribuído

## Pré-requisitos

- **Docker + Docker Compose** (recomendado)
- Python 3.10+ com honcho instalado (alternativa sem Docker)

---

## Opção A — Docker Compose (recomendado)

```bash
cd entrega
docker-compose up --build
```

Todos os serviços sobem automaticamente. O gateway fica disponível em **https://localhost:8000**.

> **Certificado auto-assinado:** na primeira vez que abrir o navegador em `https://localhost:8000/ui`,
> o browser exibirá um aviso de segurança. Clique em **Avançado → Prosseguir para localhost**
> para aceitar o certificado.

Para parar:
```bash
docker-compose down
```

Para parar e remover dados persistidos:
```bash
docker-compose down -v
```

---

## Interface Visual

Com os serviços rodando, acesse o dashboard em:

```
https://localhost:8000/ui
```

O dashboard exibe:
- **Timing System**: status em tempo real de todos os serviços (atualiza a cada 5s)
- **Merchandise**: catálogo de produtos com busca e filtro por categoria
- **Pedidos**: criação e acompanhamento de pedidos (usuários) e gerenciamento completo (admin)

---

## Opção B — Execução manual (sem Docker)

Abra **5 terminais** separados e execute cada comando abaixo.

### 1. Serviço de Usuários (porta 5001)
```bash
cd entrega/users
pip install -r requirements.txt
JWT_SECRET=minha-chave-secreta uvicorn main:app --port 5001
```

### 2. Serviço de Produtos — Réplica 1 (porta 5002)
```bash
cd entrega/products
pip install -r requirements.txt
JWT_SECRET=minha-chave-secreta SERVICE_SECRET=minha-chave-interna DB_FILE=data/products1.db uvicorn main:app --port 5002
```

### 3. Serviço de Produtos — Réplica 2 (porta 5012)
```bash
cd entrega/products
JWT_SECRET=minha-chave-secreta SERVICE_SECRET=minha-chave-interna DB_FILE=data/products2.db uvicorn main:app --port 5012
```

### 4. Serviço de Pedidos (porta 5003)
```bash
cd entrega/orders
pip install -r requirements.txt
JWT_SECRET=minha-chave-secreta SERVICE_SECRET=minha-chave-interna PRODUCTS_URL=http://localhost:8000 uvicorn main:app --port 5003
```

### 5. API Gateway (porta 8000)
```bash
cd entrega/gateway
pip install -r requirements.txt
JWT_SECRET=minha-chave-secreta \
  USERS_URL=http://localhost:5001 \
  PRODUCTS_1_URL=http://localhost:5002 \
  PRODUCTS_2_URL=http://localhost:5012 \
  ORDERS_URL=http://localhost:5003 \
  uvicorn main:app --port 8000
```

> **Atenção:** o valor de `JWT_SECRET` e `SERVICE_SECRET` deve ser **idêntico** em todos os serviços.
> Na execução manual, o gateway roda sem TLS (HTTP).

---

## Exemplos de Uso (curl)

> Todos os requests passam pelo gateway. Substitua `https` por `http` na Opção B.
> Na Opção A com TLS, use `curl -k` para aceitar o certificado auto-assinado.

### Registrar usuário comum
```bash
curl -sk -X POST https://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"João","email":"joao@email.com","password":"123456","role":"user"}'
```

### Registrar administrador
```bash
curl -sk -X POST https://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Admin","email":"admin@email.com","password":"admin123","role":"admin"}'
```

### Login (guarde o token retornado)
```bash
curl -sk -X POST https://localhost:8000/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@email.com","password":"admin123"}'
# → {"token":"<JWT>","userId":"...","role":"admin"}
```

### Criar produto (requer token de admin)
```bash
TOKEN="<JWT do admin>"
curl -sk -X POST https://localhost:8000/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Capacete Hamilton","description":"Edição 2024","price":3500.00,"stock":10,"category":"Capacetes"}'
```

### Listar produtos
```bash
curl -sk https://localhost:8000/products
```

### Criar pedido (requer token de usuário)
```bash
TOKEN="<JWT do usuário>"
PRODUCT_ID="<id do produto>"
curl -sk -X POST https://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"
```

### Verificar saúde dos serviços
```bash
curl -sk https://localhost:8000/health
```

---

## Testando Tolerância a Falhas (Heartbeat)

1. Com todos os serviços rodando, pause o serviço de pedidos:
   ```bash
   docker-compose pause orders
   ```
2. Aguarde ~10 segundos (2 ciclos de heartbeat).
3. Tente criar um pedido → resposta `503 Service Unavailable`.
4. Observe o log do gateway:
   ```bash
   docker-compose logs gateway
   # → Service 'orders' DOWN at 2026-...
   ```
5. Retome o serviço:
   ```bash
   docker-compose unpause orders
   ```
6. Aguarde ~5 segundos → gateway registra `Service 'orders' RECOVERED`.

---

## Documentação Interativa (Swagger)

FastAPI gera documentação automática para cada serviço:

| Serviço       | URL                               |
|---------------|-----------------------------------|
| Gateway       | https://localhost:8000/docs       |
| Usuários      | http://localhost:5001/docs        |
| Produtos (r1) | http://localhost:5002/docs        |
| Produtos (r2) | http://localhost:5012/docs        |
| Pedidos       | http://localhost:5003/docs        |
