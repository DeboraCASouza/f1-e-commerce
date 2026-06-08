# README de Execução — Mini E-commerce Distribuído

## Pré-requisitos

- Python 3.10+ **ou** Docker + Docker Compose

---

## Opção A — Docker Compose (recomendado)

```bash
cd entrega
docker-compose up --build
```

Todos os serviços sobem automaticamente. O gateway fica disponível em `http://localhost:8000`.

Para parar:
```bash
docker-compose down
```

---

## Opção B — Execução manual (sem Docker)

Abra **5 terminais** separados e execute cada comando abaixo em um terminal diferente.

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
JWT_SECRET=minha-chave-secreta DATA_FILE=data/products1.json uvicorn main:app --port 5002
```

### 3. Serviço de Produtos — Réplica 2 (porta 5012)
```bash
cd entrega/products
JWT_SECRET=minha-chave-secreta DATA_FILE=data/products2.json uvicorn main:app --port 5012
```

### 4. Serviço de Pedidos (porta 5003)
```bash
cd entrega/orders
pip install -r requirements.txt
JWT_SECRET=minha-chave-secreta uvicorn main:app --port 5003
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

> **Atenção:** o valor de `JWT_SECRET` deve ser **idêntico** em todos os serviços.

---

## Exemplos de Uso (curl)

> Todos os requests passam pelo gateway na porta **8000**.

### Registrar usuário comum
```bash
curl -s -X POST http://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"João","email":"joao@email.com","password":"123456","role":"user"}'
```

### Registrar administrador
```bash
curl -s -X POST http://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Admin","email":"admin@email.com","password":"admin123","role":"admin"}'
```

### Login (guarde o token retornado)
```bash
curl -s -X POST http://localhost:8000/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@email.com","password":"admin123"}'
# → {"token":"<JWT>","userId":"...","role":"admin"}
```

### Criar produto (requer token de admin)
```bash
TOKEN="<JWT do admin>"
curl -s -X POST http://localhost:8000/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Notebook","description":"16GB RAM","price":3500.00,"stock":10}'
```

### Listar produtos
```bash
curl -s http://localhost:8000/products
```

### Criar pedido (requer token de usuário)
```bash
TOKEN="<JWT do usuário>"
PRODUCT_ID="<id do produto>"
curl -s -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"
```

### Listar pedidos do usuário
```bash
TOKEN="<JWT do usuário>"
USER_ID="<id do usuário>"
curl -s http://localhost:8000/orders/$USER_ID \
  -H "Authorization: Bearer $TOKEN"
```

### Verificar saúde dos serviços
```bash
curl -s http://localhost:8000/health
```

---

## Testando Tolerância a Falhas (Heartbeat)

1. Com todos os serviços rodando, derrube o serviço de pedidos (Ctrl+C no terminal do `orders`).
2. Aguarde ~10 segundos (2 ciclos de heartbeat).
3. Tente criar um pedido via gateway → resposta `503 Service Unavailable`.
4. Observe o log do gateway registrando `Service 'orders' DOWN`.
5. Reinicie o serviço de pedidos → gateway registra `Service 'orders' RECOVERED`.

---

## Documentação Interativa

FastAPI gera automaticamente documentação Swagger para cada serviço:

| Serviço       | URL                              |
|---------------|----------------------------------|
| Gateway       | http://localhost:8000/docs       |
| Usuários      | http://localhost:5001/docs       |
| Produtos (r1) | http://localhost:5002/docs       |
| Produtos (r2) | http://localhost:5012/docs       |
| Pedidos       | http://localhost:5003/docs       |
