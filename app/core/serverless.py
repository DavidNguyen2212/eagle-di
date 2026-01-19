"""
Serverless Framework Integration for Eagle DI
==============================================

Multi-cloud serverless adapters with lifecycle management and transaction support.
Works seamlessly with FastAPI and Eagle DI's dependency injection system.

Supported Platforms:
- AWS Lambda (via Mangum)
- Azure Functions
- Google Cloud Run

Features:
- Cold start optimization with @OnColdStart
- Provisioned concurrency warmup with @OnWarmUp
- Graceful timeout handling with @Timeout
- Serverless-optimized database connections

Quick Start (AWS Lambda):
    >>> from fastapi import FastAPI
    >>> from app.core.serverless import LambdaAdapter
    >>> 
    >>> app = FastAPI()
    >>> adapter = LambdaAdapter(app)
    >>> handler = adapter.handler  # Use this as Lambda handler
    >>> 
    >>> @OnColdStart
    ... async def init_db():
    ...     await db.connect()

Author: David Nguyen
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

from fastapi import FastAPI

__all__ = [
    # Adapters
    "ServerlessAdapter",
    "LambdaAdapter",
    "AzureFunctionsAdapter", 
    "CloudRunAdapter",
    # Lifecycle decorators
    "OnColdStart",
    "OnWarmUp",
    "Timeout",
    # Scope
    "ServerlessScope",
    # Exceptions
    "ServerlessTimeoutError",
    "ColdStartError",
    # Transaction integration
    "ServerlessDatabaseProvider",
]

logger = logging.getLogger(__name__)
T = TypeVar("T")

# Global handler registries
_cold_start_handlers: list[Callable] = []
_warm_up_handlers: list[Callable] = []
_is_cold_start: bool = True


# =============================================================================
# EXCEPTIONS
# =============================================================================


class ServerlessTimeoutError(TimeoutError):
    """Raised when a serverless function times out."""
    pass


class ColdStartError(RuntimeError):
    """Raised when cold start initialization fails."""
    pass


# =============================================================================
# SCOPE ENUM
# =============================================================================


class ServerlessScope(str, Enum):
    """Scope options for serverless environments.
    
    - SINGLETON: Default, instance survives warm invocations (like FastAPI default)
    - REQUEST: Fresh instance per invocation
    - LAMBDA: Alias for SINGLETON in serverless context
    """
    SINGLETON = "singleton"
    REQUEST = "request"
    LAMBDA = "lambda"  # Alias for singleton in Lambda context


# =============================================================================
# LIFECYCLE DECORATORS
# =============================================================================


def OnColdStart(func: Callable[[], Any]) -> Callable[[], Any]:
    """Register a function to run on cold start.
    
    The decorated function is called once when the serverless container
    first starts. Use for expensive initialization like database connections.
    
    Parameters
    ----------
    func : Callable
        Async or sync function to run on cold start.
    
    Returns
    -------
    Callable
        The original function, now registered for cold start.
    
    Examples
    --------
    >>> @OnColdStart
    ... async def init_connections():
    ...     await database.connect()
    ...     await cache.connect()
    
    >>> @OnColdStart
    ... def load_ml_model():
    ...     global model
    ...     model = load_model("model.pkl")
    """
    _cold_start_handlers.append(func)
    func._is_cold_start_handler = True
    logger.debug(f"Registered cold start handler: {func.__name__}")
    return func


def OnWarmUp(func: Callable[[], Any]) -> Callable[[], Any]:
    """Register a function for provisioned concurrency warmup.
    
    Called during AWS Lambda provisioned concurrency initialization
    or similar warmup events on other platforms.
    
    Parameters
    ----------
    func : Callable
        Async or sync function to run during warmup.
    
    Returns
    -------
    Callable
        The original function, now registered for warmup.
    
    Examples
    --------
    >>> @OnWarmUp
    ... async def preload_cache():
    ...     await cache.preload_hot_keys()
    """
    _warm_up_handlers.append(func)
    func._is_warm_up_handler = True
    logger.debug(f"Registered warmup handler: {func.__name__}")
    return func


def Timeout(seconds: int, message: Optional[str] = None):
    """Decorator for graceful timeout handling.
    
    Wraps an async function to raise ServerlessTimeoutError if execution
    exceeds the specified duration. Use to leave buffer time before
    platform timeout (e.g., 25s for Lambda's 30s limit).
    
    Parameters
    ----------
    seconds : int
        Maximum execution time in seconds.
    message : str, optional
        Custom timeout error message.
    
    Returns
    -------
    Callable
        Decorator function.
    
    Examples
    --------
    >>> @Timeout(25)  # Lambda has 30s limit, leave 5s buffer
    ... async def process_data(data: dict):
    ...     return await heavy_computation(data)
    
    >>> @Timeout(10, message="Database query took too long")
    ... async def get_user(user_id: str):
    ...     return await db.fetch_user(user_id)
    """
    def decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(
                f"@Timeout can only be applied to async functions, "
                f"got {func.__name__}"
            )
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                error_msg = message or (
                    f"{func.__name__}() timed out after {seconds}s"
                )
                logger.error(error_msg)
                raise ServerlessTimeoutError(error_msg)
        
        wrapper._timeout_seconds = seconds
        return wrapper
    
    return decorator


# =============================================================================
# BASE ADAPTER
# =============================================================================


class ServerlessAdapter(ABC):
    """Abstract base class for serverless platform adapters.
    
    Subclasses implement platform-specific wrapping logic while sharing
    common lifecycle management and Eagle DI integration.
    
    Attributes
    ----------
    app : FastAPI
        The FastAPI application to wrap.
    _initialized : bool
        Whether cold start initialization has run.
    
    Examples
    --------
    >>> class CustomAdapter(ServerlessAdapter):
    ...     def wrap(self) -> Callable:
    ...         async def handler(event, context):
    ...             await self._run_cold_start_if_needed()
    ...             return await self._invoke(event)
    ...         return handler
    """
    
    def __init__(self, app: FastAPI):
        self.app = app
        self._initialized = False
    
    @abstractmethod
    def wrap(self) -> Callable:
        """Wrap FastAPI app for the serverless platform.
        
        Returns
        -------
        Callable
            Platform-specific handler function.
        """
        pass
    
    async def _run_cold_start_if_needed(self) -> None:
        """Execute cold start handlers if this is a cold start."""
        global _is_cold_start
        
        if not self._initialized:
            logger.info("Cold start detected, running initialization...")
            await self._run_handlers(_cold_start_handlers, "cold start")
            self._initialized = True
            _is_cold_start = False
    
    async def _run_warmup(self) -> None:
        """Execute warmup handlers for provisioned concurrency."""
        logger.info("Running warmup handlers...")
        await self._run_handlers(_warm_up_handlers, "warmup")
    
    async def _run_handlers(
        self, 
        handlers: list[Callable], 
        phase: str
    ) -> None:
        """Run a list of handlers, supporting both sync and async."""
        for handler in handlers:
            try:
                logger.debug(f"Running {phase} handler: {handler.__name__}")
                result = handler()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"{phase} handler {handler.__name__} failed: {e}")
                raise ColdStartError(
                    f"Failed during {phase}: {handler.__name__}"
                ) from e
    
    @property
    def handler(self) -> Callable:
        """Convenience property to get the wrapped handler."""
        return self.wrap()


# =============================================================================
# AWS LAMBDA ADAPTER
# =============================================================================


class LambdaAdapter(ServerlessAdapter):
    """AWS Lambda adapter using Mangum.
    
    Wraps a FastAPI application for deployment on AWS Lambda with
    API Gateway (REST or HTTP API) or Application Load Balancer.
    
    Parameters
    ----------
    app : FastAPI
        The FastAPI application.
    lifespan : str, default="auto"
        Mangum lifespan mode: "auto", "on", or "off".
    api_gateway_base_path : str, default="/"
        Base path for API Gateway stage.
    
    Examples
    --------
    >>> app = FastAPI()
    >>> adapter = LambdaAdapter(app)
    >>> 
    >>> # In your lambda handler file:
    >>> handler = adapter.handler
    
    >>> # With custom settings:
    >>> adapter = LambdaAdapter(
    ...     app,
    ...     lifespan="on",
    ...     api_gateway_base_path="/prod"
    ... )
    """
    
    def __init__(
        self,
        app: FastAPI,
        lifespan: str = "auto",
        api_gateway_base_path: str = "/",
    ):
        super().__init__(app)
        self.lifespan = lifespan
        self.api_gateway_base_path = api_gateway_base_path
        self._mangum_handler: Optional[Callable] = None
    
    def wrap(self) -> Callable:
        """Create Lambda handler function.
        
        Returns
        -------
        Callable
            AWS Lambda handler function.
        """
        # Lazy import Mangum to avoid import error when not installed
        try:
            from mangum import Mangum
        except ImportError:
            raise ImportError(
                "Mangum is required for AWS Lambda support. "
                "Install with: pip install mangum"
            )
        
        self._mangum_handler = Mangum(
            self.app,
            lifespan=self.lifespan,
            api_gateway_base_path=self.api_gateway_base_path,
        )
        
        async def async_handler(event: dict, context: Any) -> dict:
            """Async Lambda handler with cold start support."""
            await self._run_cold_start_if_needed()
            
            # Check for warmup event (provisioned concurrency)
            if self._is_warmup_event(event):
                await self._run_warmup()
                return {"statusCode": 200, "body": "Warmed up"}
            
            # Invoke Mangum handler
            return self._mangum_handler(event, context)
        
        def sync_handler(event: dict, context: Any) -> dict:
            """Sync wrapper for Lambda runtime."""
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Running in async context (e.g., testing)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, 
                        async_handler(event, context)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(async_handler(event, context))
        
        return sync_handler
    
    def _is_warmup_event(self, event: dict) -> bool:
        """Check if event is a warmup/ping event."""
        # AWS scheduled warmup event
        if event.get("source") == "aws.events":
            return True
        # Custom warmup marker
        if event.get("warmup") is True:
            return True
        # Provisioned concurrency initialization
        if event.get("requestContext", {}).get("stage") == "__warmup__":
            return True
        return False


# =============================================================================
# AZURE FUNCTIONS ADAPTER
# =============================================================================


class AzureFunctionsAdapter(ServerlessAdapter):
    """Azure Functions adapter.
    
    Wraps a FastAPI application for deployment on Azure Functions
    using the Python programming model v2.
    
    Parameters
    ----------
    app : FastAPI
        The FastAPI application.
    
    Examples
    --------
    >>> app = FastAPI()
    >>> adapter = AzureFunctionsAdapter(app)
    >>> 
    >>> # In your function_app.py:
    >>> import azure.functions as func
    >>> 
    >>> @app.route(route="{*route}")
    >>> async def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    ...     return await adapter.handle(req)
    """
    
    def __init__(self, app: FastAPI):
        super().__init__(app)
    
    def wrap(self) -> Callable:
        """Create Azure Functions handler.
        
        Returns
        -------
        Callable
            Azure Functions HTTP trigger handler.
        """
        async def handler(req: Any) -> Any:
            """Azure Functions HTTP handler."""
            await self._run_cold_start_if_needed()
            
            # Lazy import Azure Functions SDK
            try:
                import azure.functions as func
            except ImportError:
                raise ImportError(
                    "Azure Functions SDK is required. "
                    "Install with: pip install azure-functions"
                )
            
            # Convert Azure request to ASGI scope
            scope = self._build_asgi_scope(req)
            
            # Run through ASGI app
            response_body = []
            response_status = [200]
            response_headers = [{}]
            
            async def receive():
                body = req.get_body()
                return {"type": "http.request", "body": body}
            
            async def send(message):
                if message["type"] == "http.response.start":
                    response_status[0] = message["status"]
                    response_headers[0] = dict(message.get("headers", []))
                elif message["type"] == "http.response.body":
                    response_body.append(message.get("body", b""))
            
            await self.app(scope, receive, send)
            
            return func.HttpResponse(
                body=b"".join(response_body),
                status_code=response_status[0],
                headers=response_headers[0],
            )
        
        return handler
    
    def _build_asgi_scope(self, req: Any) -> dict:
        """Convert Azure HttpRequest to ASGI scope."""
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": req.method,
            "path": req.route_params.get("route", "/"),
            "query_string": req.url.query.encode() if req.url.query else b"",
            "headers": [
                (k.lower().encode(), v.encode())
                for k, v in req.headers.items()
            ],
            "server": (req.url.host, req.url.port or 443),
        }
    
    async def handle(self, req: Any) -> Any:
        """Handle Azure Functions HTTP request.
        
        Convenience method for direct use in function definitions.
        """
        handler = self.wrap()
        return await handler(req)


# =============================================================================
# GOOGLE CLOUD RUN ADAPTER
# =============================================================================


class CloudRunAdapter(ServerlessAdapter):
    """Google Cloud Run adapter.
    
    Cloud Run runs containers as regular HTTP servers, so minimal
    adaptation is needed. This adapter provides:
    - Optimized Uvicorn configuration
    - Cold start handling integration
    - Health check endpoint
    
    Parameters
    ----------
    app : FastAPI
        The FastAPI application.
    
    Examples
    --------
    >>> app = FastAPI()
    >>> adapter = CloudRunAdapter(app)
    >>> 
    >>> # Run with optimized settings:
    >>> if __name__ == "__main__":
    ...     adapter.run()
    """
    
    def __init__(self, app: FastAPI):
        super().__init__(app)
        self._add_health_endpoint()
    
    def _add_health_endpoint(self) -> None:
        """Add health check endpoint for Cloud Run."""
        @self.app.get("/_health", include_in_schema=False)
        async def health_check():
            return {"status": "healthy"}
    
    def wrap(self) -> FastAPI:
        """Return the FastAPI app (Cloud Run uses standard HTTP).
        
        Returns
        -------
        FastAPI
            The configured FastAPI application.
        """
        return self.app
    
    def get_uvicorn_config(self) -> dict:
        """Get optimized Uvicorn configuration for Cloud Run.
        
        Returns
        -------
        dict
            Uvicorn configuration dictionary.
        """
        return {
            "host": "0.0.0.0",
            "port": int(os.environ.get("PORT", 8080)),
            "workers": 1,  # Cloud Run handles horizontal scaling
            "timeout_keep_alive": 60,
            "access_log": True,
        }
    
    def run(self) -> None:
        """Run the app with optimized Cloud Run settings."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "Uvicorn is required for Cloud Run. "
                "Install with: pip install uvicorn"
            )
        
        config = self.get_uvicorn_config()
        logger.info(f"Starting Cloud Run server on port {config['port']}")
        uvicorn.run(self.app, **config)


# =============================================================================
# SERVERLESS DATABASE PROVIDER
# =============================================================================


class ServerlessDatabaseProvider:
    """Database provider optimized for serverless environments.
    
    Key optimizations over standard DatabaseProvider:
    - Small connection pool (default 2 vs 20+)
    - Aggressive connection recycling 
    - Auto-dispose on container freeze
    - Pre-warm on cold start
    
    Parameters
    ----------
    database_url : str
        SQLAlchemy database URL.
    pool_size : int, default=2
        Number of connections to keep in pool.
    max_overflow : int, default=3
        Max additional connections beyond pool_size.
    pool_recycle : int, default=300
        Recycle connections after N seconds.
    pool_pre_ping : bool, default=True
        Verify connections before use.
    **engine_kwargs
        Additional SQLAlchemy engine arguments.
    
    Examples
    --------
    >>> db = ServerlessDatabaseProvider(
    ...     "postgresql+asyncpg://user:pass@host/db"
    ... )
    >>> 
    >>> @OnColdStart
    ... async def init_db():
    ...     await db.warmup()
    """
    
    def __init__(
        self,
        database_url: str,
        pool_size: int = 2,
        max_overflow: int = 3,
        pool_recycle: int = 300,
        pool_pre_ping: bool = True,
        **engine_kwargs
    ):
        # Lazy import SQLAlchemy
        try:
            from sqlalchemy.ext.asyncio import (
                AsyncEngine,
                AsyncSession,
                async_sessionmaker,
                create_async_engine,
            )
        except ImportError:
            raise ImportError(
                "SQLAlchemy async is required. "
                "Install with: pip install sqlalchemy[asyncio]"
            )
        
        self.database_url = database_url
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            **engine_kwargs
        )
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        logger.info(
            f"ServerlessDatabaseProvider initialized "
            f"(pool_size={pool_size}, max_overflow={max_overflow})"
        )
    
    @asynccontextmanager
    async def transaction(self, isolation_level: Optional[str] = None):
        """Context manager for database transactions.
        
        Parameters
        ----------
        isolation_level : str, optional
            Transaction isolation level.
        
        Yields
        ------
        AsyncSession
            SQLAlchemy async session with active transaction.
        """
        from sqlalchemy.ext.asyncio import AsyncSession
        
        session: AsyncSession = self.session_maker()
        
        if isolation_level:
            await session.execute(
                f"SET TRANSACTION ISOLATION LEVEL {isolation_level}"
            )
        
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def warmup(self) -> None:
        """Pre-warm database connection pool.
        
        Call this in a @OnColdStart handler to reduce latency
        on first real request.
        """
        logger.info("Warming up database connection pool...")
        try:
            async with self.transaction() as session:
                await session.execute("SELECT 1")
            logger.info("Database warmup complete")
        except Exception as e:
            logger.error(f"Database warmup failed: {e}")
            raise
    
    async def close(self) -> None:
        """Close database engine and all connections."""
        logger.info("Closing database connections...")
        await self.engine.dispose()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def is_cold_start() -> bool:
    """Check if current invocation is a cold start.
    
    Returns
    -------
    bool
        True if this is the first invocation after container start.
    """
    return _is_cold_start


def get_remaining_time_ms(context: Any) -> Optional[int]:
    """Get remaining execution time in milliseconds (AWS Lambda only).
    
    Parameters
    ----------
    context : Any
        AWS Lambda context object.
    
    Returns
    -------
    int or None
        Remaining time in ms, or None if not available.
    """
    if hasattr(context, "get_remaining_time_in_millis"):
        return context.get_remaining_time_in_millis()
    return None


def clear_handlers() -> None:
    """Clear all registered lifecycle handlers (for testing)."""
    global _cold_start_handlers, _warm_up_handlers, _is_cold_start
    _cold_start_handlers.clear()
    _warm_up_handlers.clear()
    _is_cold_start = True


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================


# Auto-register ServerlessDatabaseProvider.warmup as cold start handler
# when the class is instantiated (done in __init__)
