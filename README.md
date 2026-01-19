# Eagle DI - Lightweight Dependency Injection for FastAPI

<p align="center">
  <img src="docs/di_logo.png" alt="DI Framework Logo" width="400">
</p>

<h2 align="center"><em>EAGLE DI</em></h2>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776ab.svg?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/FastAPI-0.95+-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI 0.95+">
  <img src="https://img.shields.io/badge/Tests-256%20passing-green.svg" alt="Tests">
</p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/💉_Modern_DI-Zero_Dependencies-4ecdc4?style=for-the-badge" alt="Modern DI"></a>
  <a href="docs/TRANSACTION.md"><img src="https://img.shields.io/badge/🔄_Transactional-Spring_Style-ff6b6b?style=for-the-badge" alt="Transactional"></a>
  <a href="docs/SERVERLESS.md"><img src="https://img.shields.io/badge/⚡_Serverless-Lambda_|_Azure_|_GCP-ff9f43?style=for-the-badge" alt="Serverless"></a>
</p>

Type hint-based DI for FastAPI. Auto-inject services without explicit `Depends()`.

**A pure Python, zero-dependency DI mini utility built specifically for FastAPI applications.**

> 📦 **Looking for more utilities?** Check out the [docs/](docs/) folder for additional features like Spring-style [`@Transactional`](docs/TRANSACTION.md) decorator and [`Serverless`](docs/SERVERLESS.md) adapters.

---

## 📥 Installation

### Option A: Copy-Paste Ready (Original Philosophy)

Just copy the file(s) you need - **zero pip install required**:

```bash
# Core DI only (~1500 lines)
cp eagle_di.py your_project/core/

# + Transaction support (~500 lines)
cp transaction.py your_project/core/

# + Serverless adapters (~800 lines)
cp serverless.py your_project/core/
```

### Option B: Install from PyPI

```bash
pip install eagle-di              # Core only
pip install eagle-di[transaction] # + @Transactional
pip install eagle-di[aws]         # + Lambda support
pip install eagle-di[serverless]  # + All serverless
```

---

## 🚀 v5.0.0 - Serverless Support

> **NEW in v5.0.0** - Deploy Eagle DI to AWS Lambda, Azure Functions, and Google Cloud Run!

### What's New

Multi-cloud serverless adapters with cold start optimization and lifecycle hooks:

```python
from fastapi import FastAPI
from app.core.serverless import LambdaAdapter, OnColdStart, Timeout

app = FastAPI()

@OnColdStart
async def init_db():
    """Runs once on cold start"""
    await database.connect()

@app.get("/users/{id}")
@Timeout(25)  # Graceful timeout (leave 5s buffer for Lambda's 30s limit)
async def get_user(id: int, service: UserService):
    return await service.get_user(id)

# AWS Lambda handler
adapter = LambdaAdapter(app)
handler = adapter.handler
```

### Supported Platforms

| Platform | Adapter | Template |
|----------|---------|----------|
| AWS Lambda | `LambdaAdapter` | `templates/serverless/aws/` |
| Azure Functions | `AzureFunctionsAdapter` | `templates/serverless/azure/` |
| Google Cloud Run | `CloudRunAdapter` | `templates/serverless/gcp/` |

### Key Features

- 🔥 **`@OnColdStart`** - Initialize connections/resources on cold start
- ⚡ **`@OnWarmUp`** - Provisioned concurrency warmup handler
- ⏱️ **`@Timeout(seconds)`** - Graceful timeout with buffer
- 🔌 **`ServerlessDatabaseProvider`** - Small pool size, aggressive recycling

> 📖 See [docs/SERVERLESS.md](docs/SERVERLESS.md) for full documentation.

---

## 🚨 v4.0.0 Breaking Changes

> **🚀 v4.0.0** - Introducing `InjectableRouter` for automatic dependency injection!

### What's New

`InjectableRouter` is a new FastAPI router that automatically handles dependency injection for all routes **without needing `@AutoInject` decorator**!

```python
# ❌ OLD WAY (v3.x) - Required @AutoInject on every route
from fastapi import APIRouter
router = APIRouter()

@router.get("/users/{id}")
@AutoInject
async def get_user(id: int, service: UserService):
    return await service.get_user(id)

# ✅ NEW WAY (v4.0) - No decorator needed!
from app.core.eagle_di import InjectableRouter
router = InjectableRouter()

@router.get("/users/{id}")  # @AutoInject not needed!
async def get_user(id: int, service: UserService):
    return await service.get_user(id)
```

### Backward Compatibility

- ✅ `@AutoInject` with `@app` routes **still works** (for simple CRUD)
- ✅ All existing v3.x code continues to work
- ✅ Migration is **optional** but recommended

### Migration Guide

1. Replace `APIRouter()` → `InjectableRouter()`
2. Remove `@AutoInject` from routes (InjectableRouter handles it automatically)
3. That's it! 🎉

## Rationale

The main reasons behind this DI framework design are:

- **Zero external dependencies** - Single file, copy-paste ready, no `pip install` needed
- **Type hint-based injection** - Let Python's type system do the wiring
- **FastAPI-native** - Seamless integration with FastAPI's `Depends()` system
- **Singleton by default** - Optimized for web applications where services are stateless

### ✅ When to use this DI

- You want a **simple, drop-in DI solution** for FastAPI
- You prefer **convention over configuration** (auto-inject by type)
- You need DI in **background workers/Celery tasks** via `get_service()`
- You want **< 1000 LOC** to understand, debug, and maintain
- You care about **startup simplicity** more than micro-optimizations

### ❌ When NOT to use this DI

- You need **transient/request scopes** (this only supports singleton)
- You require **Cython-level performance** (use `dependency-injector`)
- You want **advanced features** like conditional providers, async factories
- You need **multi-container isolation** in the same process
- Your project has **500+ injectable classes** (consider a compiled solution)

## 🚀 Quick Start

### Method 1️⃣: InjectableRouter (Recommended for Larger Projects)

Perfect for organized projects with multiple routes. **No `@AutoInject` decorator needed!**

```python
from fastapi import FastAPI
from app.core.eagle_di import Injectable, InjectableRouter, process_async_inits

# 1. Define your services
@Injectable
class UserRepository:
    async def async_init(self):
        """Called automatically during startup"""
        print("🔌 Connecting to database...")
    
    async def get_user(self, user_id: int):
        return {"id": user_id, "name": f"User{user_id}"}

@Injectable
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo  # Auto-injected!
    
    async def get_user(self, user_id: int):
        return await self.repo.get_user(user_id)

# 2. Create InjectableRouter (NOT APIRouter!)
from app.core.eagle_di import InjectableRouter
router = InjectableRouter(prefix="/api")

# 3. Define routes - dependency injection happens automatically!
@router.get("/users/{user_id}")
async def get_user(user_id: int, service: UserService):
    # UserService is auto-injected, no @AutoInject needed!
    return await service.get_user(user_id)

@router.post("/users")
async def create_user(data: dict, service: UserService):
    # Works with all FastAPI features: body, query params, headers, etc.
    return {"created": True}

# 4. Setup FastAPI app
app = FastAPI()
app.include_router(router)

@app.on_event("startup")
async def startup():
    await process_async_inits()  # Initialize all services
```

### Method 2️⃣: @AutoInject with @app Routes (For Simple CRUD)

Perfect for quick prototypes or simple services. Use `@AutoInject` decorator on routes.

```python
from fastapi import FastAPI
from app.core.eagle_di import Injectable, AutoInject, process_async_inits

# 1. Define your services (same as above)
@Injectable
class UserService:
    def get_user(self, user_id: int):
        return {"id": user_id, "name": f"User{user_id}"}

# 2. Create regular FastAPI app
app = FastAPI()

# 3. Use @AutoInject decorator on routes
@app.get("/users/{user_id}")
@AutoInject  # Add this decorator for DI
async def get_user(user_id: int, service: UserService):
    return service.get_user(user_id)

@app.post("/users")
@AutoInject  # Required for each route
async def create_user(data: dict, service: UserService):
    return {"created": True}

@app.on_event("startup")
async def startup():
    await process_async_inits()
```

**Important:** With `@app` routes, `@AutoInject` must be placed **BELOW** the route decorator:

```python
# ✅ CORRECT
@app.get("/users/{id}")
@AutoInject
def get_user(id: int, service: UserService):
    pass

# ❌ WRONG - Won't work!
@AutoInject
@app.get("/users/{id}")
def get_user(id: int, service: UserService):
    pass
```
---

## Performance Benchmarks

| Scenario | Time | Notes |
|----------|------|-------|
| Small Project (20 classes) | 1.09ms | Registration |
| Medium Project (50 classes) | 1.25ms | Registration |
| Large Project (100 classes) | 3.22ms | Registration |
| Deep Dependencies (10 levels) | 0.05ms | Resolution |
| Singleton Cache Hit | 0.0004ms | Blazing fast |
| Concurrent (10 threads) | 2.08ms | Thread-safe ✅ |
| Cold→Warm Speedup | 94x | Cached singleton |

---

## vs dependency-injector Library

| Feature | This DI | dependency-injector |
|---------|:-------:|:-------------------:|
| Auto-inject by type hint | ✅ | ❌ Manual wiring |
| Singleton scope | ✅ Default | ✅ |
| Request/Transient scope | ❌ | ✅ |
| Lifecycle hooks | ✅ | ✅ |
| Circular deps | ✅ forwardRef | ✅ |
| Testing utilities | ✅ | ✅ |
| Zero dependencies | ✅ Pure Python | ❌ Cython |
| Copy-paste ready | ✅ 1 file | ❌ pip install |
| LOC | ~1200 | ~15,000+ |

> **Summary:** 80% of features with 5% of complexity. Perfect for small-medium projects!

### Speed Benchmark (honest comparison)

| Metric | This DI | dependency-injector | Winner |
|--------|---------|---------------------|--------|
| Registration (50 classes) | 1.49ms | 1.16ms | DI Library (1.3x) |
| Resolution (1000 cached) | 0.50ms | 0.24ms | DI Library (2.1x) |
| Deep chain (5 levels) | 0.022ms | 0.011ms | DI Library (2.0x) |

> **Why?** `dependency-injector` uses **Cython** (compiled to C).
> 
> **Does it matter?** Not really! DI only runs at **startup** (once).
> Your API response time won't be affected.

---

## API Reference

| Function/Decorator | Purpose |
|-------------------|---------|
| `@Injectable` | Register a class for DI (singleton by default) |
| `InjectableRouter` | Register a router for DI (singleton by default) |
| `@AutoInject` | Auto-inject deps into FastAPI endpoint (Deprecated, now just use for @app with simple CRUD) |
| `@Controller(prefix, tags)` | Controller decorator (combines Injectable + routing for Nest/Spring fan, if you're not, just use InjectableRouter) |
| `Provide(cls)` | Explicit injection for edge cases |
| `get_service(cls)` | Get service instance programmatically |
| `forwardRef(lambda: Type)` | Lazy reference for circular deps (details below) |
| `Inject(forwardRef(...))` | TRUE circular dependency (returns getter) (details below) |

### Testing Utilities

| Function | Purpose |
|----------|---------|
| `override(cls, mock)` | Context manager to mock a provider |
| `test_container()` | Context manager for test isolation |
| `clear_registry()` | Clear all registrations (for testing) |
```python
# example
@pytest.mark.asyncio
async def test_orbit_simulation_determinism_with_service():
    """
    Test that the Orbit simulation produces deterministic results using the SimulationService.
    
    Uses DI override system to mock database dependencies while keeping
    real simulation logic intact.
    """
    from app.services.simulation.database_provider import DatabaseProvider
    from app.services.simulation.simulation_persistence_service import SimulationPersistenceService
    from app.services.simulation.config_service import ConfigService
    from app.services.simulation.here_routing_service import HereRoutingService
    from app.services.v1.orbit.lead_filter_service import LeadFilterService
    from app.services.v1.orbit.calendar_sync_service import CalendarSyncService
    
    # Create mock objects
    mock_db_provider = Mock(spec=DatabaseProvider)
    
    @asynccontextmanager
    async def mock_transaction(isolation_level=None):
        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()
        yield mock_session
    
    mock_db_provider.transaction = mock_transaction
    mock_db_provider.session = mock_transaction
    
    mock_db_service = Mock(spec=SimulationPersistenceService)
    mock_simulation_run = Mock()
    mock_simulation_run.id = "test-run-id"
    mock_db_service.save_simulation_run = AsyncMock(return_value=mock_simulation_run)
    mock_db_service.update_simulation_status = AsyncMock()
    mock_db_service.save_iterations = AsyncMock()
    mock_db_service.extract_scheduled_visits = Mock(return_value=[])
    mock_db_service.save_scheduled_visits = AsyncMock()
    
    mock_config_service = Mock(spec=ConfigService)
    mock_config = Mock()
    mock_config.id = 1
    mock_config.name = "config-1"
    mock_config.config = {}
    mock_config_service.get_config_by_id = AsyncMock(return_value=None)
    mock_config_service.create_config = AsyncMock(return_value=mock_config)
    
    mock_here_routing = Mock(spec=HereRoutingService)
    mock_here_routing.get_polyline = AsyncMock(return_value=None)
    mock_here_routing.get_route = AsyncMock(return_value=None)
    
    # Mock new services (optional for basic simulation)
    mock_lead_filter = Mock(spec=LeadFilterService)
    mock_calendar_sync = Mock(spec=CalendarSyncService)
    
    # Use DI override to inject mocks - now works because resolver skips overridden deps
    with override(DatabaseProvider, mock_db_provider), \
         override(SimulationPersistenceService, mock_db_service), \
         override(ConfigService, mock_config_service), \
         override(HereRoutingService, mock_here_routing), \
         override(LeadFilterService, mock_lead_filter), \
         override(CalendarSyncService, mock_calendar_sync):
        
        # Get SimulationService with mocked dependencies
        simulation_service = get_service(SimulationService)
        
        # Create simulation config
        config = SimulationConfig(
            calendar_id="test@example.com",
            start_date=datetime(2026, 1, 1).date(),
            weeks=6,
            max_iterations=30,
            verbose=False,
            leads_count=300
        )
        
        # Run simulation twice with the same configuration
        result_1 = await simulation_service.run(config)
        result_2 = await simulation_service.run(config)
        
        # Assert that the results are identical
        assert result_1.stats == result_2.stats, f"Simulation results differ: {result_1.stats} != {result_2.stats}"
        
        # Log the results for debugging
        print(f"Simulation results (Run 1): {result_1.stats}")
        print(f"Simulation results (Run 2): {result_2.stats}")
```


### Lifecycle

| Function | Purpose |
|----------|---------|
| `on_init()` | Method on service, called after instantiation |
| `on_destroy()` | Method on service, called during shutdown |
| `process_async_inits()` | **NEW** Await all queued async on_init() hooks |
| `async_shutdown_all()` | Call all `on_destroy()` hooks |

---

## Singleton Scope (Default)

All `@Injectable` services are **singletons by default**:

```python
@Injectable
class UserService:
    pass

# Both get the SAME instance
service1 = get_service(UserService)
service2 = get_service(UserService)
assert service1 is service2  # ✅ Same instance
```

---

## Lifecycle Hooks

```python
@Injectable
class CacheService:
    async def on_init(self):
        """Called after instantiation"""
        self.client = await connect_redis()
    
    async def on_destroy(self):
        """Called during shutdown"""
        await self.client.close()
```

Hook into FastAPI lifespan:

```python
from app.core.injector import async_shutdown_all, get_service, process_async_inits

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Eagerly init services (queues async on_init)
    _ = get_service(CacheService)
    
    # ⚠️ v2.0: Must await async on_init() hooks
    await process_async_inits()
    
    yield
    
    # Shutdown: Call all on_destroy hooks
    await async_shutdown_all()
```

---

## Programmatic Access

Use `get_service()` outside of FastAPI request context:

```python
from app.core.injector import get_service

# Background task
async def process_queue():
    service = get_service(UserService)
    await service.notify(user_id)

# CLI script
if __name__ == "__main__":
    service = get_service(MyService)
    service.run()
```

---

## Circular Dependencies

> ⚠️ **Always refactor your code to avoid circular dependencies!**  
> `forwardRef` and `Inject` should only be used as a **last resort**.

### Pattern 1: One-way with `forwardRef`

```python
def _get_a():
    from .service_a import ServiceA
    return ServiceA

@Injectable
class ServiceB:
    def __init__(self, a: forwardRef(_get_a)):
        self.a = a  # Instance of ServiceA
```

### Pattern 2: TRUE Circular with `Inject(forwardRef(...))`

```python
# service_a.py
def _get_b():
    from .service_b import ServiceB
    return ServiceB

@Injectable
class ServiceA:
    def __init__(self, get_b: Inject(forwardRef(_get_b))):
        self._get_b = get_b  # ← GETTER FUNCTION, not instance!
    
    def use_b(self):
        return self._get_b().do_something()  # ← Call when needed
```

---

## Testing Utilities

### `override()` - Mock a Provider

```python
from app.core.injector import override
from unittest.mock import Mock

def test_user_endpoint():
    mock_service = Mock()
    mock_service.get_user.return_value = {"id": 1}
    
    with override(UserService, mock_service):
        response = client.get("/users/1")
        assert response.json()["id"] == 1
    
    # Original provider restored automatically
```

### `test_container()` - Complete Isolation

```python
from app.core.injector import test_container, Injectable

def test_isolated():
    with test_container():
        @Injectable
        class TestService:
            pass
        # Fresh registry, only TestService exists
    
    # Original registry restored
```

### `clear_registry()` - Reset All

```python
@pytest.fixture(autouse=True)
def reset_di():
    yield
    clear_registry()
```

---

## Debugging

Set `DI_VERBOSE=1` to see detailed logs:

```bash
DI_VERBOSE=1 make dev
```

---

## Limitations

### ⚠️ Services with FastAPI dependencies (e.g., `db`)

Services that depend on FastAPI-specific dependencies like `db: AsyncSession = Depends(get_db)` **cannot be accessed** via `get_service()` until they've been "warmed up" by at least one HTTP request.

```python
@Injectable
class UserService:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db

# ❌ This will FAIL if no request has been made yet
service = get_service(UserService)

# ✅ After first HTTP request, singleton is cached and get_service() works
```

**Workaround for background workers:**

```python
@Injectable
class UserService:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_db)]):
        self.db = db
    
    async def process(self, db: AsyncSession | None = None):
        """
        Methods that workers will use should accept optional db param.
        - db=None (from app) → use self.db
        - db not None (from worker) → use passed db
        """
        session = db or self.db
        await session.execute(...)

# In worker:
async def background_task():
    async with async_session_maker() as session:
        service = get_service(UserService)
        await service.process(db=session)  # Pass worker's session
```

**Alternative approaches:**
- For services that need programmatic access, ensure they only depend on other `@Injectable` classes, not FastAPI `Depends()`.
- Or make a dummy HTTP request during startup to warm up the cache.

### Parameter Order Limitation

**This is a Python language constraint, not a framework limitation.**

When placing service parameters **before** required params (path, query), you must give the service a default value. This applies to **BOTH `@AutoInject` and `InjectableRouter`**.

```python
# ❌ WRONG - Python syntax error (for BOTH patterns)
@app.get("/users/{id}")
@AutoInject
def get_user(service: UserService, id: int):  # Error!
    pass

# Also fails with InjectableRouter!
router = InjectableRouter()
@router.get("/users/{id}")
def get_user(service: UserService, id: int):  # Same error!
    pass

# ✅ CORRECT - Service has default value
@app.get("/users/{id}")
@AutoInject
def get_user(service: UserService = None, id: int = Path()):
    pass

# ✅ BEST - Put service AFTER required params (cleaner!)
@app.get("/users/{id}")
@AutoInject
def get_user(id: int, service: UserService):
    pass
```

**Why?** When the framework transforms the signature, it adds `= Depends(...)` to service params. Python doesn't allow parameters without defaults to come after parameters with defaults.

```python
# What happens internally:
def get_user(service: UserService, id: int):
    pass

# Transforms to:
def get_user(service: UserService = Depends(...), id: int):  # ❌ Python error!
    pass
```

**Solution:** Always put injectable services **AFTER** required parameters!

---

## Best Practices

### ✅ Controllers (Routes/Endpoints)

**Always use explicit FastAPI parameter annotations** for clarity and better Swagger documentation:

```python
from fastapi import Path, Query, Body, Header
from app.core.eagle_di import InjectableRouter, Injectable

@Injectable
class UserService:
    def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": f"User{user_id}"}
    
    def search_users(self, query: str, limit: int) -> list:
        return [{"name": query}][:limit]

router = InjectableRouter(prefix="/api")

# ✅ GOOD - Explicit parameter annotations
@router.get("/users/{user_id}")
async def get_user(
    user_id: int = Path(..., description="User ID"),
    include_metadata: bool = Query(False, description="Include metadata"),
    service: UserService = None  # Auto-injected, can omit annotation
):
    return service.get_user(user_id)

@router.post("/users")
async def create_user(
    data: dict = Body(...),
    x_request_id: str = Header(None),
    service: UserService = None
):
    return {"created": True, "request_id": x_request_id}

# ❌ BAD - Implicit parameters (unclear in Swagger)
@router.get("/search")
async def search_users(q: str, limit: int, service: UserService):
    # Works, but Swagger won't show parameter descriptions
    return service.search_users(q, limit)
```

**Why?**
- ✅ Better Swagger/OpenAPI documentation
- ✅ Clear validation rules and descriptions
- ✅ Easier for frontend developers to understand API
- ✅ Type hints + FastAPI annotations = bulletproof API

### ✅ Services (Business Logic)

**Services should NOT use FastAPI dependencies** - keep them pure Python:

```python
from app.core.eagle_di import Injectable

# ✅ GOOD - Pure Python service
@Injectable
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo  # DI-injected service
    
    def get_user(self, user_id: int) -> dict:
        """Pure business logic - no FastAPI deps"""
        return self.repo.find_by_id(user_id)
    
    def search_users(self, query: str, limit: int = 10) -> list:
        """Simple Python parameters"""
        return self.repo.search(query, limit)

# ❌ BAD - Service with FastAPI dependencies
@Injectable
class BadUserService:
    def __init__(self, db: Annotated[Session, Depends(get_db)]):
        # ❌ Don't do this! Services should be framework-agnostic
        self.db = db
    
    def get_user(self, user_id: int = Path(...)):
        # ❌ Services shouldn't use Path/Query/Body!
        pass
```

**Why?**
- ✅ Services stay framework-agnostic (can be reused in CLI, workers, tests)
- ✅ Easier to test (no FastAPI dependencies to mock)
- ✅ Clear separation of concerns (controller = HTTP, service = business logic)
- ✅ Services accessible via `get_service()` anywhere in codebase

### ✅ Layered Architecture Pattern

```python
# ========================================
# LAYER 1: Controllers (routes.py)
# ========================================
from fastapi import Path, Query, Body
from app.core.eagle_di import InjectableRouter

router = InjectableRouter(prefix="/api/users")

@router.get("/{user_id}")
async def get_user_endpoint(
    user_id: int = Path(..., ge=1),  # FastAPI validation
    include_posts: bool = Query(False),
    service: UserService = None  # DI-injected
):
    """HTTP layer - handles request/response"""
    return await service.get_user_with_posts(user_id, include_posts)

# ========================================
# LAYER 2: Services (services/user_service.py)
# ========================================
from app.core.eagle_di import Injectable

@Injectable
class UserService:
    def __init__(self, repo: UserRepository, post_svc: PostService):
        self.repo = repo
        self.post_svc = post_svc
    
    async def get_user_with_posts(self, user_id: int, include_posts: bool) -> dict:
        """Business logic - no FastAPI deps"""
        user = await self.repo.get_by_id(user_id)
        if include_posts:
            user['posts'] = await self.post_svc.get_user_posts(user_id)
        return user

# ========================================
# LAYER 3: Repositories (repositories/user_repo.py)
# ========================================
@Injectable
class UserRepository:
    async def get_by_id(self, user_id: int) -> dict:
        """Data access - pure queries"""
        # Database logic here
        return {"id": user_id, "name": "Alice"}
```

### ✅ DO

- ✅ Use `InjectableRouter` for production apps (5+ routes)
- ✅ Put services **AFTER** required params in route signatures
- ✅ Use explicit `Path()`, `Query()`, `Body()` in controllers
- ✅ Keep services framework-agnostic (pure Python)
- ✅ Implement `async_init()` for async setup (DB connections, etc.)
- ✅ Use `get_service()` for programmatic access (workers, CLI)
- ✅ Layer architecture: Controller → Service → Repository

### ❌ DON'T

- ❌ Put service param before required params without `= None`
- ❌ Use FastAPI `Depends()` in service constructors
- ❌ Use `Path()`, `Query()`, `Body()` in service methods
- ❌ Create circular dependencies (refactor instead!)
- ❌ Call `get_service()` in `__init__` methods
- ❌ Mix business logic in controllers (keep them thin)

---

## Test Suite

Run all DI tests to verify the framework works correctly:

```bash
# Run all DI tests
pytest tests/ -v -s

# Run specific test files
pytest tests/test_injection.py -v -s      
```
### 🤔 When to Use Which Pattern?

| Pattern | Best For | Pros | Cons |
|---------|----------|------|------|
| **InjectableRouter** | Production apps, multiple routes | ✅ No decorator on routes<br>✅ Cleaner code<br>✅ Better organization | ➖ Slight overhead at router creation |
| **@AutoInject + @app** | Quick prototypes, 1-5 routes | ✅ Simple setup<br>✅ Direct routing | ➖ Decorator on every route<br>➖ Less organized |
| **@Controller** | Fans of NestJS/Spring | ✅ Familiar syntax<br>✅ Class-based<br>✅ DI in constructor | ➖ Requires registration |

**Rule of Thumb:**
- 📦 **Use `InjectableRouter`** if you have 5+ routes or are building a production app
- ⚡ **Use `@AutoInject`** for quick scripts, demos, or very simple APIs  
- 🎯 **Use `@Controller`** if you love NestJS/Spring and want class-based controllers

---

## 🎯 Method 3️⃣: @Controller (For NestJS & Spring Boot Fans)

If you're coming from **NestJS** or **Spring Boot**, you'll feel right at home with this pattern!

```python
from fastapi import FastAPI, Path, Query, Body
from app.core.eagle_di import (
    Injectable, 
    Controller, 
    Get, Post, Put, Delete, Patch,
    register_controller,
    process_async_inits
)

# 1. Define your services (same as before)
@Injectable
class UserRepository:
    def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": f"User{user_id}"}

@Injectable
class UserService:
    def __init__(self, repo: UserRepository):  # DI in constructor!
        self.repo = repo
    
    def get_user(self, user_id: int) -> dict:
        return self.repo.get_user(user_id)
    
    def create_user(self, name: str) -> dict:
        return {"created": True, "name": name}

# 2. Define Controller with NestJS-style decorators
@Controller(prefix="/api/users", tags=["Users"])
class UserController:
    def __init__(self, service: UserService):  # Service auto-injected!
        self.service = service
    
    @Get()
    def list_users(self):
        """GET /api/users"""
        return [{"id": 1}, {"id": 2}]
    
    @Get("/{user_id}")
    def get_user(self, user_id: int = Path(..., ge=1)):
        """GET /api/users/{user_id}"""
        return self.service.get_user(user_id)
    
    @Post()
    def create_user(self, data: dict = Body(...)):
        """POST /api/users"""
        return self.service.create_user(data["name"])
    
    @Put("/{user_id}")
    def update_user(self, user_id: int, data: dict = Body(...)):
        """PUT /api/users/{user_id}"""
        return {"updated": True, "id": user_id}
    
    @Delete("/{user_id}")
    def delete_user(self, user_id: int):
        """DELETE /api/users/{user_id}"""
        return {"deleted": True, "id": user_id}

# 3. Register controller with FastAPI app
app = FastAPI()
register_controller(UserController, app)

@app.on_event("startup")
async def startup():
    await process_async_inits()
```

**Multiple Controllers:**
```python
@Controller(prefix="/products", tags=["Products"])
class ProductController:
    def __init__(self, product_service: ProductService):
        self.product_service = product_service
    
    @Get()
    def list_products(self):
        return self.product_service.list_all()

app = FastAPI()
register_controller(UserController, app)
register_controller(ProductController, app)  # Multiple controllers!
```

**Why Controllers?**
- ✅ **Familiar for NestJS/Spring developers** - Same @Controller, @Get, @Post pattern
- ✅ **Class-based organization** - Services injected in constructor
- ✅ **Clean separation** - Controller handles HTTP, service handles business logic
- ✅ **All HTTP methods** - @Get, @Post, @Put, @Delete, @Patch
- ✅ **Works with all FastAPI features** - Path, Query, Body, Header parameters

---

## 📚 Test Suite

Tests are organized into logical groups for easy navigation:

```
tests/
├── core/              # Core DI functionality
├── integration/       # FastAPI integration
├── controller/        # Controller pattern
├── transaction/       # Transaction management
└── benchmarks/        # Performance tests
```

### `tests/core/` - Core DI (83 tests)

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_injection.py` | 19 | Singleton, override, circular deps |
| `test_advanced_features.py` | 23 | Advanced DI patterns & features |
| `test_edge_cases.py` | 20 | Error handling & edge scenarios |
| `test_limitations.py` | 12 | Known limitations & constraints |
| `test_async_lifecycle.py` | 9 | Async on_init/on_destroy |

### `tests/integration/` - FastAPI Integration (46 tests)

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_fastapi_integration.py` | 15 | Path, query, body, header params |
| `test_injectable_router.py` | 14 | Router-level DI injection |
| `test_backward_compatibility.py` | 12 | Legacy API compatibility |
| `test_swagger_compatible.py` | 5 | OpenAPI/Swagger integration |

### `tests/controller/` - Controller Pattern (28 tests)

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_controller.py` | 21 | Controller pattern implementation |
| `test_controller_edge_cases.py` | 7 | Controller error scenarios |

### `tests/transaction/` - Transaction Management (55 tests)

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_transaction.py` | 37 | Transaction management & rollback |
| `test_transaction_advanced.py` | 18 | Nested transactions & savepoints |

### `tests/benchmarks/` - Performance (16 tests)

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_performance.py` | 11 | Benchmarks & scalability |
| `test_benchmark_compare.py` | 5 | Performance vs dependency-injector |

---

| **Total** | **228** | ✅ All passing |