# Atividade 1 — Mini E-commerce Distribuído

Valor: 3 pontos
INDIVIDUAL

---

## Contexto

Sistemas de e-commerce reais são construídos sobre arquiteturas distribuídas compostas por diversos microsserviços independentes. Nesta atividade, você irá implementar uma versão simplificada desse tipo de sistema, aplicando na prática conceitos fundamentais de sistemas distribuídos: decomposição em microsserviços, replicação de dados, tolerância a falhas e segurança entre serviços.

---

## Objetivo

Construir um sistema de e-commerce mínimo composto por três microsserviços que se comunicam entre si, com replicação básica de dados, detecção de falha por heartbeat e autenticação via JWT.

---

## Arquitetura Esperada

```
Cliente (curl / Postman / script)
│
┌─────────▼──────────┐
│ API Gateway │ ← ponto de entrada único
└──┬──────┬──────┬───┘
│ │ │
┌──────▼─┐ ┌──▼───┐ ┌▼────────┐
│Usuários│ │Produ-│ │Pedidos │
│:5001 │ │tos │ │:5003 │
└────────┘ │:5002 │ └─────────┘
└──────┘
```

Cada microsserviço possui sua própria base de dados (arquivo JSON, SQLite ou similar). O API Gateway repassa requisições autenticadas aos serviços corretos.

---

## O que Deve Ser Implementado

### 1. Microsserviços (obrigatório)

Implemente os três serviços abaixo. Cada um deve rodar em porta separada e ser iniciado de forma independente.

#### Serviço de Usuários (`/users`)
| Endpoint | Método | Descrição |
|---|---|---|
| `/users/register` | POST | Cria novo usuário (nome, email, senha hash) |
| `/users/login` | POST | Autentica e retorna JWT |
| `/users/:id` | GET | Retorna dados do usuário (requer JWT) |

#### Serviço de Produtos (`/products`)
| Endpoint | Método | Descrição |
|---|---|---|
| `/products` | GET | Lista todos os produtos |
| `/products/:id` | GET | Detalha um produto |
| `/products` | POST | Cria produto (requer JWT de admin) |

#### Serviço de Pedidos (`/orders`)
| Endpoint | Método | Descrição |
|---|---|---|
| `/orders` | POST | Cria pedido vinculando usuário e produto |
| `/orders/:userId` | GET | Lista pedidos de um usuário (requer JWT) |

---

### 2. Replicação Simples (obrigatório)

O **Serviço de Produtos** deve manter **duas réplicas** do seu armazenamento de dados (ex: dois arquivos JSON ou dois processos rodando nas portas 5002 e 5012).

- Toda escrita (criação/atualização de produto) deve ser propagada para ambas as réplicas antes de confirmar sucesso ao cliente.
- Toda leitura pode ser feita em qualquer réplica (leitura distribuída por round-robin simples).
- Documente no relatório qual estratégia de consistência foi adotada (consistência forte ou eventual) e justifique.

---

### 3. Detecção de Falha por Heartbeat (obrigatório)

O **API Gateway** deve implementar um mecanismo simples de heartbeat:

- A cada intervalo fixo (ex: 5 segundos), o gateway envia uma requisição `GET /health` a cada microsserviço.
- Se um serviço não responder em até 2 tentativas, o gateway deve:
- Registrar a falha em log com timestamp.
- Retornar ao cliente uma mensagem de erro clara (`503 Service Unavailable`) caso esse serviço seja requisitado.
- Quando o serviço voltar a responder, o gateway deve registrar a recuperação em log.

Cada microsserviço deve expor o endpoint `GET /health` retornando `{ "status": "ok" }`.

---

### 4. Segurança com JWT (obrigatório)

- O login no Serviço de Usuários gera um token JWT assinado com uma chave secreta.
- O token deve conter: `userId`, `email`, `role` (user ou admin) e `exp` (expiração).
- Todos os endpoints marcados como "requer JWT" devem validar o token antes de processar a requisição.
- O API Gateway deve repassar o token nos headers para os serviços internos.
- Senhas devem ser armazenadas com hash (ex: bcrypt ou SHA-256).

---

## Entregáveis

```
entrega/
├── gateway/ ← código do API Gateway
├── users/ ← código do Serviço de Usuários
├── products/ ← código do Serviço de Produtos
├── orders/ ← código do Serviço de Pedidos
├── docker-compose.yml (opcional, mas valorizado)
├── README_execucao.md ← instruções para rodar o projeto
└── relatorio.pdf ← relatório escrito (ver abaixo)
```

### Relatório (1 a 2 páginas)

O relatório deve responder objetivamente:

1. Como a comunicação entre os microsserviços foi implementada? (REST, gRPC, fila, etc.)
2. Qual estratégia de consistência foi adotada na replicação? Forte ou eventual? Por quê?
3. O que acontece com o sistema se o Serviço de Pedidos cair? O restante continua funcionando?
4. Como o JWT garante que um usuário comum não consiga criar produtos?
5. Quais limitações a sua implementação possui em relação a um sistema real de produção?

---

## Tecnologias Permitidas

Qualquer linguagem ou framework. Sugestões: Node.js + Express, Python + Flask/FastAPI, Go. A comunicação entre serviços deve ser feita via HTTP/REST (mínimo). O uso de Docker é opcional, mas valorizado.

---

## Critérios de Avaliação

Consulte a **Rubrica Geral da Atividade** disponível no Classroom.

---

## Dicas

- Comece pelos microsserviços individualmente antes de integrá-los ao gateway.
- Use variáveis de ambiente para armazenar a chave secreta do JWT e portas dos serviços.
- Para simular falha, basta derrubar um dos serviços durante os testes e observar o comportamento do heartbeat.
- Não é necessário banco de dados relacional — arquivos JSON ou SQLite são suficientes.




## Penalidades

| Situação | Desconto |
|---|---|
| Sistema não executa (erro na inicialização) | −1,0 pt |
| Ausência do `README_execucao.md` ou instruções insuficientes para rodar | −0,3 pt |
| Plágio identificado (total ou parcial entre grupos) | Nota 0 para todos os envolvidos |
| Entrega em atraso (por dia corrido) | −0,3 pt/dia (máximo −1,0 pt) |

---

## Bônus (não ultrapassa 3,0 pt)

| Situação | Acréscimo |
|---|---|
| Uso de Docker Compose funcional para subir toda a infraestrutura | +0,2 pt |
| TLS/HTTPS na comunicação entre serviços | +0,2 pt |
| Interface visual (dashboard HTML simples) para monitoramento | +0,1 pt |

---

## Critérios de Execução Mínima

Para ser avaliado, o projeto deve:

1. Ser iniciado seguindo as instruções do `README_execucao.md` sem erros críticos.
2. Ter ao menos **dois microsserviços distintos** em execução e se comunicando.
3. Ter o relatório entregue junto com o código.

Projetos que não atendam a esses requisitos mínimos receberão nota máxima de **1,0 pt**, independentemente do código.

---

## Formato de Entrega

- Compactado em `.zip` com o nome `AtividadeN_NomeAluno.zip` (ex: `Atividade2_JoaoSilva.zip`).
- Ou link para repositório **privado** no GitHub com acesso concedido ao professor ou público. 
- O relatório deve ser entregue em PDF dentro do pacote.
- **Prazo:** conforme definido no Classroom.

---

## Para obter a pontuação máxima

### Decomposição e Comunicação em Microsserviço

Avalia se o sistema foi corretamente decomposto em serviços independentes que se comunicam de forma bem definida.

- Todos os microsserviços exigidos foram implementados, rodam de forma independente em processos/portas separadas, comunicam-se via HTTP/REST com contratos de API claros e documentados. Nenhum serviço depende de código compartilhado em memória com outro.

### Consistência e Replicação de Dados

Avalia a implementação da replicação de dados entre nós/instâncias e a adoção explícita de uma estratégia de consistência.

- Replicação implementada e funcional: escritas são propagadas corretamente para as réplicas. A estratégia de consistência (forte, eventual ou por quórum) está implementada conforme especificado e explicada de forma fundamentada no relatório. Leituras de réplicas retornam dados corretos.

### Tolerância a Falhas

Avalia se o sistema detecta falhas, reage a elas de forma adequada e se recupera quando o componente falho volta a operar.

- Detecção de falha implementada (heartbeat, timeout ou health check) com log registrando eventos. O sistema continua operando com funcionalidade degradada esperada quando um componente cai. Recuperação implementada: ao voltar, o componente sincroniza dados perdidos corretamente. Demonstrado em testes documentados.

### Segurança

Avalia a implementação dos mecanismos de autenticação e autorização entre clientes e serviços.

- Autenticação implementada e funcional em todos os pontos exigidos (cliente → serviço e entre serviços internos). Tokens/API Keys são validados corretamente. Requisições sem credencial ou com credencial inválida retornam os códigos HTTP apropriados (401/403). Senhas armazenadas com hash (quando aplicável).

### Relatório e Análise Crítica

Avalia a qualidade da reflexão escrita sobre as decisões de projeto, trade-offs e limitações do sistema implementado.

- Todas as perguntas do relatório são respondidas com clareza e precisão técnica. O estudante demonstra compreensão dos conceitos (consistência, tolerância a falhas, segurança) além da implementação, discute trade-offs de forma fundamentada e reconhece limitações reais do sistema.