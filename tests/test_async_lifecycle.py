"""
Async Lifecycle Tests for DI Utility
=======================================

Tests for async on_init and on_destroy lifecycle hooks.

Run with: pytest tests/unit/DI/test_async_lifecycle.py -v -s
"""

import asyncio
import pytest

from app.core.eagle_di import (
    Injectable,
    get_service,
    async_shutdown_all,
    process_async_inits,
    test_container,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def isolate_tests():
    """Each test runs in isolated container"""
    with test_container():
        yield


# =============================================================================
# Async Lifecycle Tests
# =============================================================================


class TestAsyncOnInit:
    """Tests for async on_init lifecycle hook"""

    @pytest.mark.asyncio
    async def test_async_on_init_called(self):
        """async on_init should be called after process_async_inits()"""
        init_called = []

        @Injectable
        class AsyncService:
            async def on_init(self):
                init_called.append(True)
                await asyncio.sleep(0.01)  # Simulate async work

        service = get_service(AsyncService)
        
        # Async on_init is queued, not called yet
        assert len(init_called) == 0, "on_init should be queued, not called immediately"
        
        # Process queued async inits
        await process_async_inits()
        
        assert len(init_called) == 1, "on_init should be called after process_async_inits"

    @pytest.mark.asyncio
    async def test_async_on_init_with_state(self):
        """async on_init can set up service state after process_async_inits()"""
        @Injectable
        class DatabaseService:
            def __init__(self):
                self.connected = False
            
            async def on_init(self):
                await asyncio.sleep(0.01)  # Simulate connection
                self.connected = True

        service = get_service(DatabaseService)
        
        # Not connected yet (on_init queued)
        assert service.connected is False
        
        # Process async inits
        await process_async_inits()
        
        assert service.connected is True

    @pytest.mark.asyncio
    async def test_sync_on_init_still_works(self):
        """Regular sync on_init should still work"""
        init_called = []

        @Injectable
        class SyncService:
            def on_init(self):
                init_called.append(True)

        service = get_service(SyncService)
        
        assert len(init_called) == 1


class TestAsyncOnDestroy:
    """Tests for async on_destroy lifecycle hook"""

    @pytest.mark.asyncio
    async def test_async_shutdown_all(self):
        """async_shutdown_all should call all on_destroy hooks"""
        destroyed = []

        @Injectable
        class CleanupService:
            async def on_destroy(self):
                await asyncio.sleep(0.01)  # Simulate cleanup
                destroyed.append("CleanupService")

        @Injectable
        class CacheService:
            async def on_destroy(self):
                await asyncio.sleep(0.01)
                destroyed.append("CacheService")

        # Create instances
        get_service(CleanupService)
        get_service(CacheService)

        # Shutdown
        await async_shutdown_all()

        assert "CleanupService" in destroyed
        assert "CacheService" in destroyed

    @pytest.mark.asyncio
    async def test_sync_on_destroy_with_async_shutdown(self):
        """Sync on_destroy should work with async_shutdown_all"""
        destroyed = []

        @Injectable
        class SyncCleanupService:
            def on_destroy(self):
                destroyed.append("SyncCleanupService")

        get_service(SyncCleanupService)
        await async_shutdown_all()

        assert "SyncCleanupService" in destroyed


class TestAsyncLifecycleOrder:
    """Tests for lifecycle hook execution order"""

    @pytest.mark.asyncio
    async def test_init_before_destroy(self):
        """on_init should complete before on_destroy can be called"""
        events = []

        @Injectable
        class OrderedService:
            async def on_init(self):
                events.append("init_start")
                await asyncio.sleep(0.01)
                events.append("init_end")
            
            async def on_destroy(self):
                events.append("destroy")

        get_service(OrderedService)
        await process_async_inits()  # Process queued on_init
        await async_shutdown_all()

        assert events == ["init_start", "init_end", "destroy"]

    @pytest.mark.asyncio
    async def test_service_usable_during_init(self):
        """Service should be available even while on_init is queued"""
        @Injectable
        class SlowInitService:
            def __init__(self):
                self.value = "ready"
            
            async def on_init(self):
                await asyncio.sleep(0.05)

        service = get_service(SlowInitService)
        
        # Service is immediately available (on_init is queued)
        assert service.value == "ready"
        
        # Process async inits to avoid pending coroutine warning
        await process_async_inits()


class TestAsyncErrorHandling:
    """Tests for error handling in async lifecycle"""

    @pytest.mark.asyncio
    async def test_on_init_error_doesnt_break_service(self):
        """Error in on_init should not prevent service usage"""
        @Injectable
        class FailingInitService:
            def __init__(self):
                self.value = "ok"
            
            async def on_init(self):
                raise ValueError("Init failed!")

        # Service should still be created
        service = get_service(FailingInitService)
        assert service.value == "ok"
        
        # Error is logged but doesn't raise
        await process_async_inits()

    @pytest.mark.asyncio
    async def test_on_destroy_error_doesnt_stop_others(self):
        """Error in one on_destroy shouldn't stop other cleanups"""
        destroyed = []

        @Injectable
        class FailingDestroyService:
            async def on_destroy(self):
                raise ValueError("Destroy failed!")

        @Injectable
        class GoodDestroyService:
            async def on_destroy(self):
                destroyed.append("good")

        get_service(FailingDestroyService)
        get_service(GoodDestroyService)

        # Should not raise, should continue cleanup
        await async_shutdown_all()

        assert "good" in destroyed
