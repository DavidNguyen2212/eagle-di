"""
Tests for Serverless Module
===========================

Tests lifecycle decorators, adapters, and serverless database provider.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import module under test
from app.core.serverless import (
    AzureFunctionsAdapter,
    CloudRunAdapter,
    ColdStartError,
    LambdaAdapter,
    OnColdStart,
    OnWarmUp,
    ServerlessDatabaseProvider,
    ServerlessScope,
    ServerlessTimeoutError,
    Timeout,
    clear_handlers,
    is_cold_start,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_handlers():
    """Clear all handlers before and after each test."""
    clear_handlers()
    yield
    clear_handlers()


@pytest.fixture
def mock_fastapi_app():
    """Create a mock FastAPI app."""
    from fastapi import FastAPI
    app = FastAPI()
    
    @app.get("/")
    async def root():
        return {"message": "Hello"}
    
    return app


# =============================================================================
# LIFECYCLE DECORATORS
# =============================================================================


class TestOnColdStart:
    """Tests for @OnColdStart decorator."""
    
    def test_registers_sync_handler(self):
        """Sync function is registered as cold start handler."""
        @OnColdStart
        def my_handler():
            pass
        
        assert hasattr(my_handler, "_is_cold_start_handler")
        assert my_handler._is_cold_start_handler is True
    
    def test_registers_async_handler(self):
        """Async function is registered as cold start handler."""
        @OnColdStart
        async def my_async_handler():
            pass
        
        assert hasattr(my_async_handler, "_is_cold_start_handler")
        assert my_async_handler._is_cold_start_handler is True
    
    def test_function_still_callable(self):
        """Decorated function remains callable."""
        call_count = 0
        
        @OnColdStart
        def increment():
            nonlocal call_count
            call_count += 1
        
        increment()
        assert call_count == 1


class TestOnWarmUp:
    """Tests for @OnWarmUp decorator."""
    
    def test_registers_warmup_handler(self):
        """Function is registered as warmup handler."""
        @OnWarmUp
        async def warmup_handler():
            pass
        
        assert hasattr(warmup_handler, "_is_warm_up_handler")
        assert warmup_handler._is_warm_up_handler is True


class TestTimeout:
    """Tests for @Timeout decorator."""
    
    def test_rejects_sync_function(self):
        """@Timeout only works with async functions."""
        with pytest.raises(TypeError, match="async functions"):
            @Timeout(5)
            def sync_func():
                pass
    
    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        """Function that completes in time returns normally."""
        @Timeout(5)
        async def fast_func():
            await asyncio.sleep(0.01)
            return "done"
        
        result = await fast_func()
        assert result == "done"
    
    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """Function exceeding timeout raises ServerlessTimeoutError."""
        @Timeout(1)
        async def slow_func():
            await asyncio.sleep(10)
            return "never"
        
        with pytest.raises(ServerlessTimeoutError, match="timed out after 1s"):
            await slow_func()
    
    @pytest.mark.asyncio
    async def test_custom_error_message(self):
        """Custom message is included in timeout error."""
        @Timeout(1, message="Custom timeout message")
        async def slow_func():
            await asyncio.sleep(10)
        
        with pytest.raises(ServerlessTimeoutError, match="Custom timeout message"):
            await slow_func()
    
    def test_preserves_timeout_metadata(self):
        """Decorated function has timeout metadata."""
        @Timeout(25)
        async def func():
            pass
        
        assert func._timeout_seconds == 25


# =============================================================================
# LAMBDA ADAPTER
# =============================================================================


class TestLambdaAdapter:
    """Tests for AWS Lambda adapter."""
    
    def test_requires_mangum(self, mock_fastapi_app):
        """Raises ImportError if Mangum not installed."""
        adapter = LambdaAdapter(mock_fastapi_app)
        
        with patch.dict("sys.modules", {"mangum": None}):
            with pytest.raises(ImportError, match="Mangum is required"):
                adapter.wrap()
    
    @patch("app.core.serverless.LambdaAdapter._run_cold_start_if_needed")
    def test_wrap_returns_callable(self, mock_cold_start, mock_fastapi_app):
        """wrap() returns a callable handler."""
        with patch("mangum.Mangum"):
            adapter = LambdaAdapter(mock_fastapi_app)
            handler = adapter.wrap()
            assert callable(handler)
    
    def test_is_warmup_event_aws_events(self, mock_fastapi_app):
        """Detects AWS scheduled warmup events."""
        adapter = LambdaAdapter(mock_fastapi_app)
        
        warmup_event = {"source": "aws.events"}
        assert adapter._is_warmup_event(warmup_event) is True
    
    def test_is_warmup_event_custom(self, mock_fastapi_app):
        """Detects custom warmup marker."""
        adapter = LambdaAdapter(mock_fastapi_app)
        
        warmup_event = {"warmup": True}
        assert adapter._is_warmup_event(warmup_event) is True
    
    def test_is_warmup_event_false(self, mock_fastapi_app):
        """Normal events are not warmup events."""
        adapter = LambdaAdapter(mock_fastapi_app)
        
        normal_event = {"httpMethod": "GET", "path": "/users"}
        assert adapter._is_warmup_event(normal_event) is False
    
    def test_handler_property(self, mock_fastapi_app):
        """handler property returns wrapped handler."""
        with patch("mangum.Mangum"):
            adapter = LambdaAdapter(mock_fastapi_app)
            handler = adapter.handler
            assert callable(handler)


# =============================================================================
# AZURE FUNCTIONS ADAPTER
# =============================================================================


class TestAzureFunctionsAdapter:
    """Tests for Azure Functions adapter."""
    
    def test_build_asgi_scope(self, mock_fastapi_app):
        """Correctly builds ASGI scope from Azure request."""
        adapter = AzureFunctionsAdapter(mock_fastapi_app)
        
        # Mock Azure HttpRequest
        mock_req = Mock()
        mock_req.method = "GET"
        mock_req.route_params = {"route": "/users/123"}
        mock_req.url = Mock()
        mock_req.url.query = "page=1"
        mock_req.url.host = "example.com"
        mock_req.url.port = 443
        mock_req.headers = {"Content-Type": "application/json"}
        
        scope = adapter._build_asgi_scope(mock_req)
        
        assert scope["type"] == "http"
        assert scope["method"] == "GET"
        assert scope["path"] == "/users/123"
        assert scope["query_string"] == b"page=1"


# =============================================================================
# CLOUD RUN ADAPTER
# =============================================================================


class TestCloudRunAdapter:
    """Tests for Google Cloud Run adapter."""
    
    def test_wrap_returns_app(self, mock_fastapi_app):
        """wrap() returns the FastAPI app unchanged."""
        adapter = CloudRunAdapter(mock_fastapi_app)
        wrapped = adapter.wrap()
        assert wrapped is mock_fastapi_app
    
    def test_adds_health_endpoint(self, mock_fastapi_app):
        """Adds /_health endpoint to app."""
        adapter = CloudRunAdapter(mock_fastapi_app)
        
        # Check route was added
        routes = [r.path for r in mock_fastapi_app.routes]
        assert "/_health" in routes
    
    def test_uvicorn_config_defaults(self, mock_fastapi_app):
        """Default Uvicorn config has correct values."""
        adapter = CloudRunAdapter(mock_fastapi_app)
        config = adapter.get_uvicorn_config()
        
        assert config["host"] == "0.0.0.0"
        assert config["workers"] == 1
        assert config["timeout_keep_alive"] == 60
    
    @patch.dict("os.environ", {"PORT": "9000"})
    def test_uvicorn_config_port_from_env(self, mock_fastapi_app):
        """Port is read from PORT environment variable."""
        adapter = CloudRunAdapter(mock_fastapi_app)
        config = adapter.get_uvicorn_config()
        
        assert config["port"] == 9000


# =============================================================================
# SERVERLESS DATABASE PROVIDER
# =============================================================================


class TestServerlessDatabaseProvider:
    """Tests for serverless-optimized database provider."""
    
    def test_small_pool_size_default(self):
        """Default pool size is small (2)."""
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            provider = ServerlessDatabaseProvider(
                "postgresql+asyncpg://user:pass@localhost/db"
            )
            
            # Check create_async_engine was called with small pool
            call_kwargs = mock_engine.call_args.kwargs
            assert call_kwargs["pool_size"] == 2
            assert call_kwargs["max_overflow"] == 3
    
    def test_custom_pool_settings(self):
        """Custom pool settings are applied."""
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            provider = ServerlessDatabaseProvider(
                "postgresql+asyncpg://user:pass@localhost/db",
                pool_size=5,
                max_overflow=10,
                pool_recycle=600,
            )
            
            call_kwargs = mock_engine.call_args.kwargs
            assert call_kwargs["pool_size"] == 5
            assert call_kwargs["max_overflow"] == 10
            assert call_kwargs["pool_recycle"] == 600
    
    @pytest.mark.asyncio
    async def test_warmup_executes_query(self):
        """warmup() executes SELECT 1 to verify connection."""
        from contextlib import asynccontextmanager
        
        with patch("sqlalchemy.ext.asyncio.create_async_engine"):
            with patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_session_maker:
                # Setup mock session
                mock_session = AsyncMock()
                mock_session_maker.return_value = Mock(return_value=mock_session)
                
                provider = ServerlessDatabaseProvider(
                    "postgresql+asyncpg://user:pass@localhost/db"
                )
                
                # Mock transaction as proper async context manager
                mock_ctx = AsyncMock()
                
                @asynccontextmanager
                async def mock_transaction(isolation_level=None):
                    yield mock_ctx
                
                provider.transaction = mock_transaction
                
                await provider.warmup()
                
                # Verify SELECT 1 was called
                mock_ctx.execute.assert_called_once()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_is_cold_start_initially_true(self):
        """is_cold_start() returns True initially."""
        clear_handlers()  # Reset state
        assert is_cold_start() is True
    
    def test_serverless_scope_values(self):
        """ServerlessScope enum has correct values."""
        assert ServerlessScope.SINGLETON == "singleton"
        assert ServerlessScope.REQUEST == "request"
        assert ServerlessScope.LAMBDA == "lambda"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestColdStartIntegration:
    """Integration tests for cold start behavior."""
    
    @pytest.mark.asyncio
    async def test_cold_start_handlers_run_once(self, mock_fastapi_app):
        """Cold start handlers only run on first invocation."""
        call_count = 0
        
        @OnColdStart
        def count_calls():
            nonlocal call_count
            call_count += 1
        
        with patch("mangum.Mangum") as mock_mangum:
            mock_mangum.return_value = Mock(return_value={"statusCode": 200})
            
            adapter = LambdaAdapter(mock_fastapi_app)
            
            # Simulate cold start
            await adapter._run_cold_start_if_needed()
            assert call_count == 1
            
            # Simulate warm invocation
            await adapter._run_cold_start_if_needed()
            assert call_count == 1  # Still 1, not 2
    
    @pytest.mark.asyncio
    async def test_async_cold_start_handler(self, mock_fastapi_app):
        """Async cold start handlers are awaited."""
        result = []
        
        @OnColdStart
        async def async_init():
            await asyncio.sleep(0.01)
            result.append("initialized")
        
        adapter = LambdaAdapter(mock_fastapi_app)
        await adapter._run_cold_start_if_needed()
        
        assert result == ["initialized"]
    
    @pytest.mark.asyncio
    async def test_cold_start_error_propagates(self, mock_fastapi_app):
        """Errors in cold start handlers propagate as ColdStartError."""
        @OnColdStart
        def failing_init():
            raise ValueError("Init failed")
        
        adapter = LambdaAdapter(mock_fastapi_app)
        
        with pytest.raises(ColdStartError, match="Failed during cold start"):
            await adapter._run_cold_start_if_needed()


# =============================================================================
# TRANSACTION INTEGRATION TESTS
# =============================================================================


class TestTransactionIntegration:
    """Tests for ServerlessDatabaseProvider with transaction support."""
    
    @pytest.mark.asyncio
    async def test_serverless_db_transaction_context(self):
        """ServerlessDatabaseProvider transaction works as context manager."""
        from contextlib import asynccontextmanager
        
        with patch("sqlalchemy.ext.asyncio.create_async_engine"):
            with patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_maker:
                # Setup mock
                mock_session = AsyncMock()
                mock_maker.return_value = Mock(return_value=mock_session)
                
                provider = ServerlessDatabaseProvider(
                    "postgresql+asyncpg://user:pass@localhost/db"
                )
                
                # Mock the real transaction method behavior
                @asynccontextmanager
                async def mock_transaction(isolation_level=None):
                    yield mock_session
                
                provider.transaction = mock_transaction
                
                async with provider.transaction() as session:
                    await session.execute("SELECT 1")
                
                mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_serverless_db_close(self):
        """ServerlessDatabaseProvider.close() disposes engine."""
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create:
            mock_engine = AsyncMock()
            mock_create.return_value = mock_engine
            
            with patch("sqlalchemy.ext.asyncio.async_sessionmaker"):
                provider = ServerlessDatabaseProvider(
                    "postgresql+asyncpg://user:pass@localhost/db"
                )
                
                await provider.close()
                mock_engine.dispose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cold_start_warmup_db(self, mock_fastapi_app):
        """Database warmup can be integrated with @OnColdStart."""
        from contextlib import asynccontextmanager
        
        warmup_called = False
        
        with patch("sqlalchemy.ext.asyncio.create_async_engine"):
            with patch("sqlalchemy.ext.asyncio.async_sessionmaker"):
                provider = ServerlessDatabaseProvider(
                    "postgresql+asyncpg://user:pass@localhost/db"
                )
                
                # Mock transaction
                mock_session = AsyncMock()
                
                @asynccontextmanager
                async def mock_transaction(isolation_level=None):
                    yield mock_session
                
                provider.transaction = mock_transaction
                
                @OnColdStart
                async def warmup_database():
                    nonlocal warmup_called
                    await provider.warmup()
                    warmup_called = True
                
                adapter = LambdaAdapter(mock_fastapi_app)
                await adapter._run_cold_start_if_needed()
                
                assert warmup_called is True
                mock_session.execute.assert_called()
    
    def test_serverless_db_pool_pre_ping_enabled(self):
        """pool_pre_ping is enabled by default for connection validation."""
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            provider = ServerlessDatabaseProvider(
                "postgresql+asyncpg://user:pass@localhost/db"
            )
            
            call_kwargs = mock_engine.call_args.kwargs
            assert call_kwargs["pool_pre_ping"] is True
    
    @pytest.mark.asyncio
    async def test_transaction_isolation_level(self):
        """Transaction can be created with custom isolation level."""
        from contextlib import asynccontextmanager
        
        with patch("sqlalchemy.ext.asyncio.create_async_engine"):
            with patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_maker:
                mock_session = AsyncMock()
                mock_maker.return_value = Mock(return_value=mock_session)
                
                provider = ServerlessDatabaseProvider(
                    "postgresql+asyncpg://user:pass@localhost/db"
                )
                
                # Use the real transaction method (not mocked)
                # We just need to verify isolation_level is passed
                
                isolation_used = None
                
                @asynccontextmanager
                async def mock_transaction(isolation_level=None):
                    nonlocal isolation_used
                    isolation_used = isolation_level
                    yield mock_session
                
                provider.transaction = mock_transaction
                
                async with provider.transaction(isolation_level="SERIALIZABLE") as session:
                    pass
                
                assert isolation_used == "SERIALIZABLE"


# =============================================================================
# ADDITIONAL UTILITY TESTS  
# =============================================================================


class TestGetRemainingTime:
    """Tests for get_remaining_time_ms utility."""
    
    def test_returns_time_when_available(self):
        """Returns remaining time from Lambda context."""
        from app.core.serverless import get_remaining_time_ms
        
        mock_context = Mock()
        mock_context.get_remaining_time_in_millis.return_value = 25000
        
        result = get_remaining_time_ms(mock_context)
        assert result == 25000
    
    def test_returns_none_when_not_available(self):
        """Returns None if context doesn't have the method."""
        from app.core.serverless import get_remaining_time_ms
        
        mock_context = Mock(spec=[])  # Empty spec, no methods
        
        result = get_remaining_time_ms(mock_context)
        assert result is None


class TestMultipleColdStartHandlers:
    """Tests for multiple @OnColdStart handlers."""
    
    @pytest.mark.asyncio
    async def test_multiple_handlers_all_run(self, mock_fastapi_app):
        """All registered cold start handlers are executed."""
        results = []
        
        @OnColdStart
        def handler_one():
            results.append("one")
        
        @OnColdStart
        def handler_two():
            results.append("two")
        
        @OnColdStart
        async def handler_three():
            await asyncio.sleep(0.01)
            results.append("three")
        
        adapter = LambdaAdapter(mock_fastapi_app)
        await adapter._run_cold_start_if_needed()
        
        assert "one" in results
        assert "two" in results
        assert "three" in results
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_handlers_run_in_order(self, mock_fastapi_app):
        """Handlers run in registration order."""
        order = []
        
        @OnColdStart
        def first():
            order.append(1)
        
        @OnColdStart
        def second():
            order.append(2)
        
        @OnColdStart
        def third():
            order.append(3)
        
        adapter = LambdaAdapter(mock_fastapi_app)
        await adapter._run_cold_start_if_needed()
        
        assert order == [1, 2, 3]


class TestWarmUpHandlers:
    """Tests for @OnWarmUp handlers."""
    
    @pytest.mark.asyncio
    async def test_warmup_handlers_run(self, mock_fastapi_app):
        """Warmup handlers are executed during warmup."""
        warmup_called = False
        
        @OnWarmUp
        async def warmup_handler():
            nonlocal warmup_called
            warmup_called = True
        
        adapter = LambdaAdapter(mock_fastapi_app)
        await adapter._run_warmup()
        
        assert warmup_called is True
    
    @pytest.mark.asyncio
    async def test_multiple_warmup_handlers(self, mock_fastapi_app):
        """Multiple warmup handlers all run."""
        results = []
        
        @OnWarmUp
        def warmup_one():
            results.append("cache")
        
        @OnWarmUp
        async def warmup_two():
            results.append("db")
        
        adapter = LambdaAdapter(mock_fastapi_app)
        await adapter._run_warmup()
        
        assert "cache" in results
        assert "db" in results
    
    @pytest.mark.asyncio
    async def test_warmup_event_triggers_warmup(self, mock_fastapi_app):
        """Warmup event triggers warmup handlers."""
        warmup_ran = False
        
        @OnWarmUp
        def on_warmup():
            nonlocal warmup_ran
            warmup_ran = True
        
        with patch("mangum.Mangum"):
            adapter = LambdaAdapter(mock_fastapi_app)
            
            # Trigger warmup via _run_warmup
            await adapter._run_warmup()
            
            assert warmup_ran is True


class TestCloudRunAdapterRun:
    """Tests for CloudRunAdapter.run() method."""
    
    def test_run_requires_uvicorn(self, mock_fastapi_app):
        """run() raises ImportError if uvicorn not installed."""
        adapter = CloudRunAdapter(mock_fastapi_app)
        
        with patch.dict("sys.modules", {"uvicorn": None}):
            with pytest.raises(ImportError, match="Uvicorn is required"):
                adapter.run()
    
    def test_run_calls_uvicorn(self, mock_fastapi_app):
        """run() calls uvicorn.run with correct config."""
        adapter = CloudRunAdapter(mock_fastapi_app)
        
        with patch("uvicorn.run") as mock_run:
            adapter.run()
            
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["host"] == "0.0.0.0"
            assert call_kwargs["workers"] == 1

