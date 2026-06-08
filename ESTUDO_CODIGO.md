# Guia de Estudo — Mini E-commerce Distribuído

> Use este documento para entender o código antes de conversar com o professor.

---

## Visão Geral da Arquitetura

O sistema tem **5 processos** rodando em paralelo:

```
Cliente (curl / Postman / Navegador)
            │
    ┌───────▼────────┐  porta 8000
    │  API Gateway   │  ← único ponto de entrada
    └──┬──────┬──────┬┘
       │      │      │
    :5001  :5002  :5003
    Users  Prods  Orders
           :5012
         (réplica)
```

Cada serviço é um arquivo Python independente (`main.py`) usando **FastAPI**. Cada um tem seu próprio banco de dados SQLite. Eles **não compartilham memória** — só conversam via HTTP.

---

## Serviço de Usuários — `users/main.py`

### O que ele faz
Guarda usuários no banco, cuida de login e emite tokens JWT.

### Banco de dados (linhas 41–49)
```python
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,   ← senha nunca é guardada em texto puro
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
)
```

### Senhas com bcrypt (linhas 25–29)
```python
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())
```
**Requisito atendido:** a especificação pede bcrypt ou SHA-256. Usamos bcrypt, que é mais seguro.

### Geração do JWT (linhas 73–80)
```python
def create_token(user) -> str:
    payload = {
        "userId": user["id"],
        "email":  user["email"],
        "role":   user["role"],   ← "user" ou "admin"
        "exp":    datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
```
**Requisito atendido:** o payload contém `userId`, `email`, `role` e `exp`, exatamente como pedido.

### Verificação do JWT (linhas 83–87)
```python
def verify_token(credentials) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```
Qualquer endpoint protegido chama `Depends(verify_token)`. Se o token for inválido ou expirado → 401.

### Endpoints
| Método | Rota | Auth | Código |
|--------|------|------|--------|
| POST | `/users/register` | — | linha 95 |
| POST | `/users/login` | — | linha 118 |
| GET | `/users/{id}` | JWT | linha 128 |

---

## Serviço de Produtos — `products/main.py`

O **mesmo arquivo** `main.py` é usado para as duas réplicas. A diferença é a variável de ambiente `DB_FILE` (uma aponta para `products1.db`, a outra para `products2.db`).

### Verificação de admin (linhas 69–76)
```python
def verify_admin(credentials) -> dict:
    payload = jwt.decode(credentials.credentials, JWT_SECRET, ...)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload
```
**Requisito atendido:** criar produto (`POST /products`) exige role `admin`. Um usuário comum recebe 403.

### Criação de produto (linhas 134–156)
O endpoint aceita um `id` opcional no body. Isso é importante porque o **Gateway** gera o `id` e manda o mesmo para as duas réplicas, garantindo que ambas tenham o produto com o mesmo identificador.

### Atualização de estoque (linhas 159–188)
```python
@app.patch("/products/{product_id}/stock")
def update_stock(product_id: str, req: StockUpdate, x_service_secret: Optional[str] = Header(None)):
    if x_service_secret != SERVICE_SECRET:
        raise HTTPException(status_code=403, ...)
```
Esse endpoint **não aceita JWT** — só aceita requisições vindas de outros serviços internos que conhecem o `SERVICE_SECRET`. Isso evita que um usuário externo manipule o estoque diretamente.

A lógica de decremento (linha 170–178) verifica se há estoque suficiente antes de subtrair:
```python
"UPDATE products SET stock = stock + ? WHERE id = ? AND stock >= ?"
```
Se não houver estoque → 409 Conflict.

---

## Gateway — `gateway/main.py`

O Gateway é o componente mais complexo. Ele implementa três requisitos ao mesmo tempo: **heartbeat**, **round-robin de leitura** e **replicação de escrita**.

### Registro dos serviços (linhas 20–25)
```python
SERVICES = {
    "users":      {"url": "http://localhost:5001", "healthy": True, "failures": 0},
    "products_1": {"url": "http://localhost:5002", "healthy": True, "failures": 0},
    "products_2": {"url": "http://localhost:5012", "healthy": True, "failures": 0},
    "orders":     {"url": "http://localhost:5003", "healthy": True, "failures": 0},
}
```
Cada serviço tem três campos: a URL, se está saudável, e quantas falhas consecutivas acumulou.

---

### HEARTBEAT (linhas 31–57)

**Requisito:** a cada 5 segundos, o gateway manda `GET /health` para cada serviço. Se falhar 2 vezes seguidas, marca como down e loga com timestamp.

```python
async def check_service(name: str, svc: dict):
    url = f"{svc['url']}/health"
    for attempt in range(2):          # tenta 2 vezes
        try:
            resp = await client.get(url, timeout=2.0)
            if resp.status_code == 200:
                if not svc["healthy"]:
                    logger.info(f"Service '{name}' RECOVERED at {datetime.utcnow()...}")
                svc["healthy"] = True
                svc["failures"] = 0
                return
        except Exception:
            pass
        if attempt == 0:
            await asyncio.sleep(0.3)   # espera 300ms entre tentativas

    svc["failures"] += 1
    if svc["healthy"]:
        logger.error(f"Service '{name}' DOWN at {datetime.utcnow()...}")
    svc["healthy"] = False
```

```python
async def heartbeat_loop():
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)   # 5 segundos
        await asyncio.gather(*[check_service(n, s) for n, s in SERVICES.items()])
```

O loop é iniciado quando o app sobe (via `lifespan`, linhas 60–68) e cancelado quando o app para.

**Recuperação:** quando o serviço volta, o log registra `RECOVERED` e as requisições voltam a funcionar automaticamente.

---

### ROUND-ROBIN de leitura (linhas 90–97)

```python
_product_rr = 0   # contador global

def _pick_replica():
    global _product_rr
    healthy = [s for k, s in SERVICES.items() if k.startswith("products_") and s["healthy"]]
    if not healthy:
        return None
    svc = healthy[_product_rr % len(healthy)]
    _product_rr += 1
    return svc
```

- Requisição 1 → réplica 1
- Requisição 2 → réplica 2
- Requisição 3 → réplica 1
- ... e assim por diante.

Se uma réplica estiver down, o round-robin usa só a saudável.

---

### REPLICAÇÃO FORTE de escrita (linhas 151–179)

**Requisito:** escritas devem ser propagadas para **ambas** as réplicas antes de confirmar para o cliente.

```python
@app.post("/products")
async def proxy_products_write(request: Request):
    p1, p2 = SERVICES["products_1"], SERVICES["products_2"]
    if not p1["healthy"] or not p2["healthy"]:
        return JSONResponse({"detail": "Cannot write: a product replica is unavailable"}, 503)

    body_json["id"] = str(uuid.uuid4())   # gera o mesmo id para as duas

    r1, r2 = await asyncio.gather(        # envia para as duas AO MESMO TEMPO
        client.post(f"{p1['url']}/products", ...),
        client.post(f"{p2['url']}/products", ...),
    )

    if r1.status_code not in (200, 201) or r2.status_code not in (200, 201):
        logger.error("Product replication failed")
        return JSONResponse({"detail": "Replication failed"}, 500)
```

**Estratégia de consistência: FORTE.** O gateway só retorna sucesso se as **duas** réplicas confirmarem. Se qualquer uma falhar, retorna erro 500. Isso garante que nunca haverá produto em uma réplica e não na outra.

---

### ROLLBACK de estoque (linhas 182–219)

Quando um pedido é criado, o serviço de Orders chama o gateway para decrementar o estoque. O gateway replica esse decremento nas duas réplicas. Se uma réplica confirmar e a outra falhar, o gateway **reverte** a que confirmou:

```python
rollback = json.dumps({"delta": -body_json["delta"]}).encode()
if ok1 and not ok2:
    await client.patch(f"{p1['url']}/products/{product_id}/stock", content=rollback)
```

---

### Proxy geral (linhas 100–116)

Para users e orders, o gateway simplesmente repassa a requisição sem modificá-la, mantendo todos os headers (incluindo o `Authorization: Bearer <token>`):

```python
def _fwd_headers(request: Request) -> dict:
    return {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
```

---

## Serviço de Pedidos — `orders/main.py`

### Criação de pedido (linhas 108–124)

```python
@app.post("/orders", status_code=201)
async def create_order(req: OrderCreate, token: dict = Depends(verify_token)):
    await patch_stock(req.product_id, -req.quantity)   # decrementa estoque ANTES
    # só salva o pedido se o estoque foi decrementado com sucesso
    db.execute("INSERT INTO orders ...")
```

A sequência é importante: primeiro reserva o estoque, depois cria o pedido. Se o estoque for insuficiente, o pedido não é criado.

### Controle de acesso nos pedidos (linhas 134–142)
```python
@app.get("/orders/{user_id}")
def get_user_orders(user_id: str, token: dict = Depends(verify_token)):
    if token["userId"] != user_id and token.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
```
Um usuário só vê seus próprios pedidos. Um admin vê de qualquer um.

### Máquina de estados (linhas 26–33)
```python
VALID_TRANSITIONS = {
    "pending":   {"confirmed", "cancelled"},
    "confirmed": {"shipped",   "cancelled"},
    "shipped":   {"delivered"},
    "delivered": set(),   # estado final
    "cancelled": set(),   # estado final
}
```
Isso vai além do requisito mínimo — impede transições inválidas de status.

### Restauração de estoque ao cancelar (linhas 164–165)
Se um pedido em `pending` ou `confirmed` for cancelado, o estoque é devolvido automaticamente.

---

## Docker Compose — `docker-compose.yml`

O arquivo sobe todos os 5 serviços com um único comando. Pontos importantes:

- Cada serviço tem seu próprio volume de dados (os bancos SQLite persistem entre restarts).
- O gateway sabe o endereço de cada serviço via variáveis de ambiente (`USERS_URL`, `PRODUCTS_1_URL`, etc.).
- `depends_on` garante que o gateway só sobe depois dos demais.

**Atenção — possível problema a discutir com o professor:** o `docker-compose.yml` define `DATA_FILE=data/products.json` para os serviços de produto, mas o código usa a variável `DB_FILE` (para SQLite). Isso significa que o Docker não passa o caminho do banco corretamente — o serviço usa o valor padrão hardcoded. Da mesma forma, `SERVICE_SECRET` e `PRODUCTS_URL` (para o serviço de orders) não estão no compose.

---

## Resumo dos Requisitos Atendidos

| Requisito | Onde está no código | Status |
|-----------|--------------------|----|
| `GET /health` em todos os serviços | `users/main.py:90`, `products/main.py:79`, `orders/main.py:103`, `gateway/main.py:119` | ✅ |
| Heartbeat a cada 5s | `gateway/main.py:54–57` | ✅ |
| Log de falha com timestamp | `gateway/main.py:49–50` | ✅ |
| 503 quando serviço está down | `gateway/main.py:131, 144, 229` | ✅ |
| Log de recuperação | `gateway/main.py:39` | ✅ |
| Round-robin entre réplicas | `gateway/main.py:90–97, 141–146` | ✅ |
| Escrita nas duas réplicas antes de confirmar | `gateway/main.py:151–179` | ✅ |
| JWT com userId, email, role, exp | `users/main.py:73–80` | ✅ |
| JWT_SECRET em variável de ambiente | `users/main.py:14`, `products/main.py:14`, `orders/main.py:14` | ✅ |
| 401 para token inválido | `users/main.py:87`, `products/main.py:72`, `orders/main.py:78` | ✅ |
| 403 para role insuficiente | `products/main.py:75`, `orders/main.py:158` | ✅ |
| Senha com bcrypt | `users/main.py:25–29` | ✅ |
| Banco separado por serviço | SQLite isolado por serviço | ✅ |
| `README_execucao.md` | Arquivo presente com opções Docker e manual | ✅ |
| Docker Compose (+0.2 pt bônus) | `docker-compose.yml` presente | ✅ |

---

## Respostas para o Relatório (as 5 perguntas)

**1. Como foi implementada a comunicação entre serviços?**
REST/HTTP síncrono. O gateway recebe as requisições dos clientes e repassa para os microserviços usando a biblioteca `httpx` (cliente HTTP assíncrono). Os serviços não se comunicam diretamente entre si, exceto o Orders que chama o gateway para atualizar estoque.

**2. Qual estratégia de consistência foi usada na replicação? Forte ou eventual?**
**Forte.** O gateway só confirma a criação de um produto quando **ambas** as réplicas respondem com sucesso (`asyncio.gather` + verificação de ambos os status codes). Se qualquer réplica falhar, a operação é rejeitada com erro 500. Isso evita divergência entre réplicas, mas tem custo: se uma réplica cair, escritas ficam bloqueadas.

**3. O que acontece se o serviço de Orders cair?**
O gateway detecta a queda no próximo ciclo de heartbeat (até 5 segundos). A partir daí, toda requisição para `/orders` recebe 503. Os demais serviços (Users e Products) continuam funcionando normalmente — a falha é isolada. Quando Orders se recuperar, o gateway detecta automaticamente e retorna ao normal.

**4. Como o JWT impede um usuário comum de criar produtos?**
No login, o token JWT é gerado com o campo `role` = `"user"` ou `"admin"`. Quando chega um `POST /products`, o gateway repassa o token para o serviço de Products. Lá, a função `verify_admin` decodifica o token e verifica se `role == "admin"`. Se for `"user"`, retorna 403. O usuário não consegue falsificar o role porque o token é assinado com `JWT_SECRET` — alterar qualquer campo invalida a assinatura.

**5. Quais limitações essa implementação tem em relação a um sistema real de produção?**
- **Sem HTTPS:** comunicação em texto puro, vulnerável a interceptação.
- **SQLite não é distribuído:** um banco real usaria PostgreSQL com replicação nativa.
- **Consistência forte bloqueia escritas:** se uma réplica cair, não é possível criar produtos. Em produção, usaria um mecanismo de reconciliação assíncrona.
- **Sem retry automático:** se uma réplica falhar na metade da replicação, não há tentativa de reenvio automático com backoff.
- **SERVICE_SECRET em texto puro:** em produção, usaria mTLS (certificados) para autenticação entre serviços.
- **Gateway é ponto único de falha:** se o gateway cair, todo o sistema para.
- **Sem autenticação na atualização de estoque via gateway externo:** o endpoint `PATCH /products/{id}/stock` no gateway não exige JWT, só `SERVICE_SECRET`, que é um segredo fraco.
