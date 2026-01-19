# Serverless Deployment Guide

Deploy Eagle DI FastAPI applications to AWS Lambda, Azure Functions, and Google Cloud Run.

## Table of Contents

- [Quick Start](#quick-start)
- [AWS Lambda](#aws-lambda)
- [Azure Functions](#azure-functions)
- [Google Cloud Run](#google-cloud-run)
- [Lifecycle Hooks](#lifecycle-hooks)
- [Database Connections](#database-connections)
- [Best Practices](#best-practices)

---

## Quick Start

```python
from fastapi import FastAPI
from app.core.serverless import LambdaAdapter, OnColdStart

app = FastAPI()

@OnColdStart
async def init():
    await database.connect()

adapter = LambdaAdapter(app)
handler = adapter.handler  # Export this for Lambda
```

---

## AWS Lambda

### Installation

```bash
pip install mangum
```

### Basic Setup

```python
# app/main.py
from fastapi import FastAPI
from app.core.serverless import LambdaAdapter, OnColdStart
from app.core.eagle_di import Injectable, InjectableRouter

app = FastAPI()

@Injectable
class UserService:
    async def get_user(self, id: int):
        return {"id": id, "name": f"User {id}"}

router = InjectableRouter()

@router.get("/users/{id}")
async def get_user(id: int, service: UserService):
    return await service.get_user(id)

app.include_router(router)

# Create handler
adapter = LambdaAdapter(app)
handler = adapter.handler
```

### Deploy with SAM

```bash
# Install SAM CLI
pip install aws-sam-cli

# Copy template
cp templates/serverless/aws/template.yaml .

# Deploy
sam build
sam deploy --guided
```

### Deploy with Serverless Framework

```bash
# Install
npm install -g serverless
pip install serverless-python-requirements

# Copy config
cp templates/serverless/aws/serverless.yml .

# Deploy
serverless deploy --stage dev
```

### LambdaAdapter Options

```python
adapter = LambdaAdapter(
    app,
    lifespan="auto",           # "auto", "on", "off"
    api_gateway_base_path="/", # API Gateway stage path
)
```

---

## Azure Functions

### Installation

```bash
pip install azure-functions
```

### Setup

```python
# function_app.py
import azure.functions as func
from fastapi import FastAPI
from app.core.serverless import AzureFunctionsAdapter, OnColdStart

app = FastAPI()
adapter = AzureFunctionsAdapter(app)

@OnColdStart
async def init():
    await database.connect()

function_app = func.FunctionApp()

@function_app.route(route="{*route}")
async def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    return await adapter.handle(req)
```

### Deploy

```bash
# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4

# Create function app in Azure Portal, then:
func azure functionapp publish <app-name>
```

---

## Google Cloud Run

Cloud Run runs containers as HTTP servers - minimal adaptation needed.

### Setup

```python
# main.py
from fastapi import FastAPI
from app.core.serverless import CloudRunAdapter, OnColdStart

app = FastAPI()
adapter = CloudRunAdapter(app)

@OnColdStart
async def init():
    await database.connect()

if __name__ == "__main__":
    adapter.run()  # Uses optimized Uvicorn config
```

### Deploy

```bash
# Option 1: Source deploy
gcloud run deploy eagle-di-api --source . --region us-central1

# Option 2: Docker
docker build -t gcr.io/PROJECT/eagle-di-api -f templates/serverless/gcp/Dockerfile .
docker push gcr.io/PROJECT/eagle-di-api
gcloud run deploy eagle-di-api --image gcr.io/PROJECT/eagle-di-api
```

---

## Lifecycle Hooks

### @OnColdStart

Runs once when container starts. Use for expensive initialization.

```python
from app.core.serverless import OnColdStart

@OnColdStart
async def init_connections():
    await database.connect()
    await redis.connect()
    load_ml_model()

@OnColdStart
def load_config():
    # Sync functions also supported
    global config
    config = load_from_ssm()
```

### @OnWarmUp

Runs during provisioned concurrency warmup (AWS Lambda).

```python
from app.core.serverless import OnWarmUp

@OnWarmUp
async def preload_cache():
    await cache.preload_hot_keys()
```

### @Timeout

Graceful timeout handling with buffer.

```python
from app.core.serverless import Timeout

@Timeout(25)  # Lambda has 30s limit, leave 5s buffer
async def process_data(data: dict):
    return await heavy_computation(data)

@Timeout(10, message="Query took too long")
async def get_user(id: int):
    return await db.fetch_user(id)
```

---

## Database Connections

### ServerlessDatabaseProvider

Optimized for serverless with small pool and aggressive recycling.

```python
from app.core.serverless import ServerlessDatabaseProvider, OnColdStart

db = ServerlessDatabaseProvider(
    "postgresql+asyncpg://user:pass@host/db",
    pool_size=2,        # Small pool (default: 2)
    max_overflow=3,     # Max additional connections
    pool_recycle=300,   # Recycle after 5 min
)

@OnColdStart
async def init_db():
    await db.warmup()  # Pre-warm connection
```

### Transaction Usage

```python
async with db.transaction() as session:
    result = await session.execute(query)
    await session.commit()
```

### With Eagle DI's @Transactional

```python
from app.core.transaction import Transactional
from app.core.serverless import ServerlessDatabaseProvider

@Injectable
class UserService:
    def __init__(self, db: ServerlessDatabaseProvider):
        self._db = db
    
    @Transactional
    async def create_user(self, data: dict, db=None):
        user = User(**data)
        db.add(user)
        return user
```

---

## Best Practices

### 1. Minimize Cold Start Time

```python
# ✅ Lazy imports for heavy libraries
@OnColdStart
def load_ml():
    global model
    import tensorflow  # Import only when needed
    model = tensorflow.saved_model.load("model")

# ❌ Don't import at module level
import tensorflow  # Increases cold start
```

### 2. Use Small Connection Pools

```python
# ✅ Serverless-optimized
db = ServerlessDatabaseProvider(url, pool_size=2)

# ❌ Default pools are too large
db = DatabaseProvider(url, pool_size=20)  # Wastes resources
```

### 3. Set Appropriate Timeouts

```python
# ✅ Leave buffer for cleanup
@Timeout(25)  # Lambda: 30s limit → 25s timeout
async def handler():
    pass

# ❌ No timeout → may hit hard limit
async def handler():
    await possibly_slow_operation()
```

### 4. Handle Provisioned Concurrency

```python
from app.core.serverless import OnWarmUp

@OnWarmUp
async def warmup():
    # Pre-warm caches, connections for provisioned concurrency
    await db.warmup()
    await cache.preload()
```

### 5. Environment Variables

```python
import os

DATABASE_URL = os.environ.get("DATABASE_URL")
STAGE = os.environ.get("STAGE", "dev")

# Don't hardcode secrets!
```

---

## Comparison

| Platform | Cold Start | Scaling | Cost Model |
|----------|------------|---------|------------|
| AWS Lambda | 100-500ms | Auto (concurrent) | Per-request |
| Azure Functions | 200-800ms | Auto (concurrent) | Per-request |
| Cloud Run | 0-2s | Auto (instances) | Per-request + min instances |

### When to Use What

- **AWS Lambda**: Best for event-driven, short-lived functions
- **Azure Functions**: Good Azure ecosystem integration
- **Cloud Run**: Best for longer requests, containers, WebSockets

---

## Troubleshooting

### Cold Start Too Slow

1. Reduce package size (use `--slim` in serverless-python-requirements)
2. Move heavy imports to `@OnColdStart`
3. Enable provisioned concurrency

### Database Connection Errors

1. Use `ServerlessDatabaseProvider` with small pool
2. Enable `pool_pre_ping=True`
3. Increase `pool_recycle` if using RDS Proxy

### Timeout Errors

1. Add `@Timeout` decorator with buffer
2. Check CloudWatch/logs for actual execution time
3. Optimize slow database queries

---

## Templates

Pre-configured templates available in `templates/serverless/`:

```
templates/serverless/
├── aws/
│   ├── template.yaml       # SAM template
│   ├── serverless.yml      # Serverless Framework
│   └── main_example.py     # Entry point example
├── azure/
│   ├── host.json           # Azure config
│   └── function_app.py     # Entry point example
└── gcp/
    ├── Dockerfile          # Cloud Run container
    └── service.yaml        # Knative config
```
