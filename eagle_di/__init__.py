"""
Eagle DI - Lightweight Dependency Injection for FastAPI
========================================================

Type hint-based DI for FastAPI. Auto-inject services without explicit `Depends()`.

Installation:
    pip install eagle-di              # Core only
    pip install eagle-di[transaction] # + @Transactional
    pip install eagle-di[serverless]  # + Lambda/Azure/GCP

Quick Start:
    >>> from eagle_di import Injectable, InjectableRouter
    >>> 
    >>> @Injectable
    ... class UserService:
    ...     def get_user(self, id: int):
    ...         return {"id": id}
    >>> 
    >>> router = InjectableRouter()
    >>> 
    >>> @router.get("/users/{id}")
    >>> async def get_user(id: int, service: UserService):
    ...     return service.get_user(id)
"""

__version__ = "5.0.1"

# =============================================================================
# CORE DI (always available)
# =============================================================================

from app.core.eagle_di import (
    # Core decorators
    Injectable,
    AutoInject,
    Controller,
    # Router
    InjectableRouter,
    # Utilities
    Inject,
    ForwardRef,
    forwardRef,
    # Container operations
    get_service,
    reset,
    override,
    test_container,
    process_async_inits,
    call_on_destroy,
    # Registry access
    get_registry,
)

__all__ = [
    # Core
    "Injectable",
    "AutoInject", 
    "Controller",
    # Router
    "InjectableRouter",
    # Utilities
    "Inject",
    "ForwardRef",
    "forwardRef",
    # Container
    "get_service",
    "reset",
    "override",
    "test_container",
    "process_async_inits",
    "call_on_destroy",
    "get_registry",
]

# =============================================================================
# TRANSACTION (optional: pip install eagle-di[transaction])
# =============================================================================

try:
    from app.core.transaction import (
        Transactional,
        transactional,
        DatabaseProvider,
        TransactionContext,
        Propagation,
        Isolation,
    )
    
    __all__ += [
        "Transactional",
        "transactional",
        "DatabaseProvider",
        "TransactionContext",
        "Propagation",
        "Isolation",
    ]
    
    _HAS_TRANSACTION = True
except ImportError:
    _HAS_TRANSACTION = False

# =============================================================================
# SERVERLESS (optional: pip install eagle-di[serverless])
# =============================================================================

try:
    from app.core.serverless import (
        # Adapters
        ServerlessAdapter,
        LambdaAdapter,
        AzureFunctionsAdapter,
        CloudRunAdapter,
        # Lifecycle
        OnColdStart,
        OnWarmUp,
        Timeout,
        # Scope
        ServerlessScope,
        # Database
        ServerlessDatabaseProvider,
        # Exceptions
        ServerlessTimeoutError,
        ColdStartError,
        # Utils
        is_cold_start,
        get_remaining_time_ms,
        clear_handlers,
    )
    
    __all__ += [
        # Adapters
        "ServerlessAdapter",
        "LambdaAdapter",
        "AzureFunctionsAdapter",
        "CloudRunAdapter",
        # Lifecycle
        "OnColdStart",
        "OnWarmUp",
        "Timeout",
        # Scope
        "ServerlessScope",
        # Database
        "ServerlessDatabaseProvider",
        # Exceptions
        "ServerlessTimeoutError",
        "ColdStartError",
        # Utils
        "is_cold_start",
        "get_remaining_time_ms",
        "clear_handlers",
    ]
    
    _HAS_SERVERLESS = True
except ImportError:
    _HAS_SERVERLESS = False


def has_transaction() -> bool:
    """Check if transaction extras are installed."""
    return _HAS_TRANSACTION


def has_serverless() -> bool:
    """Check if serverless extras are installed."""
    return _HAS_SERVERLESS
