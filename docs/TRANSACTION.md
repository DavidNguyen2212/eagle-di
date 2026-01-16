# @Transactional Decorator - Spring-Style Transaction Management

<p align="center">
  <img src="di_logo.png" alt="DI Framework Logo" width="200">
</p>

<h3 align="center"><em>Spring-style @Transactional for FastAPI + SQLAlchemy</em></h3>

<p align="center">
  <img src="https://img.shields.io/badge/SQLAlchemy-Async-blue.svg" alt="SQLAlchemy Async">
  <img src="https://img.shields.io/badge/Tests-55%20passing-green.svg" alt="Tests">
</p>

Standalone transaction management system inspired by Spring's `@Transactional`, designed to work seamlessly with FastAPI and SQLAlchemy async.

---

## Features

- ✅ **7 Propagation Behaviors** - REQUIRED, REQUIRES_NEW, MANDATORY, SUPPORTS, NOT_SUPPORTED, NEVER, NESTED
- ✅ **4 Isolation Levels** - READ_UNCOMMITTED → SERIALIZABLE
- ✅ **Rollback Rules** - Custom `rollback_for` and `no_rollback_for` exceptions
- ✅ **Timeout Support** - Configurable transaction timeout with asyncio
- ✅ **NESTED Transactions** - Savepoint support for partial rollbacks
- ✅ **DI Integration** - Works seamlessly with Eagle DI framework

---

## Quick Start

```python
from app.core.transaction import Transactional, Propagation, DatabaseProvider
from app.core.eagle_di import Injectable

@Injectable
class UserService:
    def __init__(self, db: DatabaseProvider):
        self._db = db  # Required! @Transactional uses self._db
    
    @Transactional
    async def create_user(self, data: dict, db=None):
        """Auto-commit on success, auto-rollback on exception"""
        user = User(**data)
        db.add(user)
        await db.flush()
        return user
```

---

## API Reference

### `@Transactional` Decorator

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `propagation` | `str` | `Propagation.REQUIRED` | Transaction propagation behavior |
| `isolation` | `str` | `None` | Transaction isolation level |
| `timeout` | `int` | `None` | Timeout in seconds |
| `read_only` | `bool` | `False` | Read-only optimization hint |
| `rollback_for` | `tuple[Exception, ...]` | `(Exception,)` | Exceptions that trigger rollback |
| `no_rollback_for` | `tuple[Exception, ...]` | `()` | Exceptions that should NOT rollback |

### Usage Patterns

```python
# ✅ Basic - join existing or create new (default)
@Transactional
async def create_user(self, data: dict, db=None):
    ...

# ✅ With explicit parameters
@Transactional(propagation=Propagation.REQUIRES_NEW, timeout=30)
async def audit_log(self, action: str, db=None):
    ...
```

---

## Propagation Behaviors

| Propagation | Description |
|------------|-------------|
| `REQUIRED` | Join existing transaction or create new (default) |
| `REQUIRES_NEW` | Always create new transaction, suspend current |
| `MANDATORY` | Must run in existing transaction, error if none |
| `SUPPORTS` | Join if transaction exists, otherwise run without |
| `NOT_SUPPORTED` | Always run without transaction, suspend current |
| `NEVER` | Must NOT run in transaction, error if one exists |
| `NESTED` | Create savepoint if parent transaction exists |

### Examples

**REQUIRED (Default)**
```python
@Transactional  # Same as @Transactional(propagation=Propagation.REQUIRED)
async def create_user(self, data: dict, db=None):
    user = User(**data)
    db.add(user)
    return user
```

**REQUIRES_NEW** - Audit logs that must always persist
```python
@Transactional(propagation=Propagation.REQUIRES_NEW)
async def audit_log(self, action: str, db=None):
    """Commits even if parent transaction rolls back"""
    log = AuditLog(action=action)
    db.add(log)
```

**NESTED** - Partial rollback with savepoints
```python
@Transactional(propagation=Propagation.NESTED)
async def try_update_user(self, user_id: int, data: dict, db=None):
    """If this fails, only this operation rolls back (not entire transaction)"""
    await db.execute(update(User).where(User.id == user_id).values(**data))
```

**MANDATORY** - Must be called within existing transaction
```python
@Transactional(propagation=Propagation.MANDATORY)
async def update_balance(self, account_id: int, amount: float, db=None):
    """Raises RuntimeError if no parent transaction exists"""
    ...
```

---

## Isolation Levels

| Level | Description | Dirty Read | Non-Repeatable Read | Phantom Read |
|-------|-------------|:----------:|:-------------------:|:------------:|
| `READ_UNCOMMITTED` | Lowest, allows dirty reads | ✅ | ✅ | ✅ |
| `READ_COMMITTED` | PostgreSQL default | ❌ | ✅ | ✅ |
| `REPEATABLE_READ` | MySQL default | ❌ | ❌ | ✅ |
| `SERIALIZABLE` | Highest, full isolation | ❌ | ❌ | ❌ |

```python
from app.core.transaction import Transactional, Isolation

@Transactional(isolation=Isolation.SERIALIZABLE)
async def transfer_funds(self, from_id: int, to_id: int, amount: float, db=None):
    """Full isolation for financial transactions"""
    ...
```

---

## Rollback Rules

Control which exceptions trigger rollback:

```python
@Transactional(
    rollback_for=(ValueError, KeyError),      # Rollback on these
    no_rollback_for=(UserNotFoundException,)  # Commit despite these
)
async def update_user(self, user_id: str, data: dict, db=None):
    if not data.get("name"):
        raise ValueError("Name required")  # → Rollback
    
    user = await self.find_user(user_id)
    if not user:
        raise UserNotFoundException()  # → Commit anyway (no rollback)
    
    ...
```

---

## Timeout Support

```python
@Transactional(timeout=30)  # 30 seconds
async def long_operation(self, data: dict, db=None):
    """Raises TimeoutError if exceeds 30 seconds"""
    ...
```

---

## DatabaseProvider

Connection and transaction management provider using SQLAlchemy async.

```python
from app.core.transaction import DatabaseProvider

# Initialize
db_provider = DatabaseProvider(
    "postgresql+asyncpg://user:pass@localhost/db",
    echo=True,
    pool_size=20
)

# Manual transaction control
async with db_provider.transaction() as session:
    user = User(name="John")
    session.add(user)
    # Auto-commit on exit, auto-rollback on exception

# With isolation level
async with db_provider.transaction(isolation_level=Isolation.SERIALIZABLE) as session:
    ...

# Savepoints (nested transactions)
async with db_provider.transaction() as session:
    user = User(name="John")
    session.add(user)
    
    async with db_provider.savepoint(session, "sp1"):
        # If this fails, only this block rolls back
        profile = Profile(user_id=user.id)
        session.add(profile)

# Cleanup
await db_provider.close()
```

---

## Integration with Eagle DI

The `@Transactional` decorator integrates seamlessly with the DI framework:

```python
from app.core.eagle_di import Injectable, get_service
from app.core.transaction import Transactional, DatabaseProvider

@Injectable
class UserRepository:
    def __init__(self, db: DatabaseProvider):
        self._db = db  # ⚠️ Required for @Transactional
    
    @Transactional
    async def create_user(self, name: str, db=None):
        user = User(name=name)
        db.add(user)
        await db.flush()
        return user

@Injectable
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo
    
    async def register_user(self, data: dict):
        # UserRepository handles transaction automatically
        return await self.repo.create_user(data["name"])

# Usage
service = get_service(UserService)
user = await service.register_user({"name": "John"})
```

---

## Testing Utilities

### `TransactionTestContext`

Automatic rollback after each test:

```python
from app.core.transaction import TransactionTestContext

async def test_create_user():
    db_provider = get_service(DatabaseProvider)
    
    async with TransactionTestContext(db_provider) as ctx:
        service = get_service(UserService)
        
        # All operations use the same session
        user = await service.create_user({"name": "Test"}, db=ctx.session)
        
        assert user.name == "Test"
        # Auto-rollback on exit - no data persisted to DB
```

---

## Requirements

**Service must have `self._db` attribute:**

```python
@Injectable
class MyService:
    def __init__(self, db: DatabaseProvider):
        self._db = db  # ⚠️ Required!
    
    @Transactional
    async def my_method(self, data, db=None):
        # 'db' parameter receives the session
        ...
```

**Method signature must include `db=None` parameter:**

```python
# ✅ Correct
@Transactional
async def create_user(self, data: dict, db=None):
    ...

# ❌ Wrong - missing db parameter
@Transactional
async def create_user(self, data: dict):
    ...
```

---

## Test Suite

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_transaction.py` | 37 | Core transaction management |
| `test_transaction_advanced.py` | 18 | Nested transactions & savepoints |
| **Total** | **55** | ✅ All passing |

Run tests:

```bash
pytest tests/test_transaction.py tests/test_transaction_advanced.py -v
```

---

## Comparison with Spring

| Feature | Spring @Transactional | This Implementation |
|---------|----------------------|---------------------|
| Propagation modes | ✅ 7 modes | ✅ 7 modes (identical) |
| Isolation levels | ✅ 4 levels | ✅ 4 levels (identical) |
| Rollback rules | ✅ | ✅ |
| Read-only hint | ✅ | ✅ (basic) |
| Timeout | ✅ | ✅ (via asyncio) |
| Nested/Savepoints | ✅ | ✅ |
| Async support | ❌ | ✅ Native async |
| Dependencies | Spring Framework | 0 (pure Python) |

---

## When to Use

### ✅ Use `@Transactional` when:
- You need automatic commit/rollback
- You want Spring-style propagation control
- You need nested transactions (savepoints)
- You want centralized transaction management

### ❌ Don't use when:
- Simple one-off queries (use raw session)
- Performance-critical hot paths (minor overhead)
- You need connection pooling beyond SQLAlchemy defaults
