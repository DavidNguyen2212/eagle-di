# 🔧 Class-level Dependency Injection

<p align="center">
  <img src="docs/di_logo.png" alt="DI Framework Logo" width="400">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776ab.svg?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/FastAPI-0.95+-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI 0.95+">
  <img src="https://img.shields.io/badge/Tests-59%20passing-green.svg" alt="Tests">
</p>

Type hint-based DI for FastAPI. Auto-inject services without explicit `Depends()`.

**A pure Python, zero-dependency DI mini utility built specifically for FastAPI applications.**

---

## 📦 Installation

### Prerequisites

- Python 3.9 or higher
- `uv` package manager (recommended)

### Step 1: Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip
pip install uv
```

### Step 2: Create Virtual Environment

```bash
# Create a new virtual environment with uv
uv venv

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Install from requirements.txt
uv pip install -r requirements.txt

# Or install FastAPI directly
uv pip install fastapi uvicorn[standard]
```

### Step 4: Copy DI Framework

Since this is a **zero-dependency, single-file framework**, simply copy `eagle_di.py` to your project:

```bash
# Create core directory
mkdir -p app/core

# Copy the DI framework
cp eagle_di.py app/core/

# Or download directly
curl -o app/core/eagle_di.py https://raw.githubusercontent.com/your-repo/eagle_di.py
```

### Verify Installation

```bash
# Test that everything works
python -c "from app.core.eagle_di import Injectable; print('✅ DI Framework ready!')"
```

---

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

## Quick Start

```python
from app.core.eagle_di import Injectable, AutoInject

# 1. Mark class as injectable
@Injectable
class UserService:
    def get_user(self, id: str):
        return {"id": id}

# 2. Auto-inject into other services
@Injectable
class OrderService:
    def __init__(self, user_service: UserService):  # ← Auto-injected!
        self.user_service = user_service

# 3. Use in FastAPI endpoints
@router.get("/orders/{id}")
@AutoInject
async def get_order(id: str, order_service: OrderService):  # ← Auto-injected!
    return order_service.get(id)
```

---

## Performance Benchmarks

| Scenario | Time | Notes |
|----------|------|-------|
| Small Project (20 classes) | 16ms | Registration |
| Medium Project (50 classes) | 60ms | Registration |
| Large Project (100 classes) | 94ms | Registration |
| Deep Dependencies (10 levels) | 1.4ms | Resolution |
| Singleton Cache Hit | 0.001ms | Blazing fast |
| Concurrent (10 threads) | 8ms | Thread-safe ✅ |

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
| LOC | ~780 | ~15,000+ |

> **Summary:** 80% of features with 5% of complexity. Perfect for small-medium projects!

### Speed Benchmark (honest comparison)

| Metric | This DI | dependency-injector | Winner |
|--------|---------|---------------------|--------|
| Registration (50 classes) | 52ms | 1ms | DI Library (46x) |
| Resolution (1000 cached) | 9ms | 0.5ms | DI Library (18x) |
| Deep chain (5 levels) | 0.24ms | 0.03ms | DI Library (8x) |

> **Why?** `dependency-injector` uses **Cython** (compiled to C).
> 
> **Does it matter?** Not really! DI only runs at **startup** (once).
> Your API response time won't be affected.

---

## API Reference

| Function/Decorator | Purpose |
|-------------------|---------|
| `@Injectable` | Register a class for DI (singleton by default) |
| `@AutoInject` | Auto-inject deps into FastAPI endpoint |
| `@Controller(prefix, tags)` | Controller decorator (combines Injectable + routing) |
| `Provide(cls)` | Explicit injection for edge cases |
| `get_service(cls)` | Get service instance programmatically |
| `forwardRef(lambda: Type)` | Lazy reference for circular deps |
| `Inject(forwardRef(...))` | TRUE circular dependency (returns getter) |

### Testing Utilities

| Function | Purpose |
|----------|---------|
| `override(cls, mock)` | Context manager to mock a provider |
| `test_container()` | Context manager for test isolation |
| `clear_registry()` | Clear all registrations (for testing) |

### Lifecycle

| Function | Purpose |
|----------|---------|
| `on_init()` | Method on service, called after instantiation |
| `on_destroy()` | Method on service, called during shutdown |
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
from app.core.eagle_di import async_shutdown_all, get_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Eagerly init services that need on_init
    _ = get_service(CacheService)
    
    yield
    
    # Shutdown: Call all on_destroy hooks
    await async_shutdown_all()
```

---

## Programmatic Access

Use `get_service()` outside of FastAPI request context:

```python
from app.core.eagle_di import get_service

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
from app.core.eagle_di import override
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
from app.core.eagle_di import test_container, Injectable

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

When placing service parameters **before** required params (path, query), you must give the service a default value:

```python
# ❌ WRONG - Python syntax error
@app.get("/users/{id}")
@AutoInject
def get_user(service: UserService, id: int):  # Error!
    pass

# ✅ CORRECT - Service has default value
@app.get("/users/{id}")
@AutoInject
def get_user(service: UserService = None, id: int = Path()):
    pass

# ✅ BEST - Put service AFTER required params
@app.get("/users/{id}")
@AutoInject
def get_user(id: int, service: UserService):
    pass
```

---

## Best Practices

### ✅ DO

- Use `@Injectable` for all services
- Use `@AutoInject` for FastAPI endpoints
- Put services **after** required params (path, query)
- Use `get_service()` for background tasks
- Implement `on_destroy()` for cleanup

### ❌ DON'T

- Put service param before required params without `= None`
- Abuse `forwardRef` - this is a code smell
- Call getter in `__init__`
- Create long circular chains (A→B→C→D→A)

---

## Test Suite

Run all DI tests to verify the framework works correctly:

```bash
# Run all DI tests
pytest tests/ -v

# Run specific test files
pytest tests/test_injection.py -v       # Core functionality (13 tests)
pytest tests/test_performance.py -v -s  # Benchmarks (10 tests)
pytest tests/test_fastapi_integration.py -v  # FastAPI params (15 tests)
pytest tests/test_async_lifecycle.py -v  # Async lifecycle (9 tests)
pytest tests/test_benchmark_compare.py -v  # vs dependency-injector (5 tests)
```

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_injection.py` | 13 | Core DI (singleton, override, circular deps) |
| `test_performance.py` | 10 | Benchmarks & scalability |
| `test_fastapi_integration.py` | 15 | Path, query, body, header params |
| `test_async_lifecycle.py` | 9 | Async on_init/on_destroy |
| `test_benchmark_compare.py` | 5 | Comparison with dependency-injector |
| **Total** | **52** | ✅ All passing |