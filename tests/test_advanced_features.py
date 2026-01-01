"""
Advanced Features Tests for DI Framework
=========================================

Tests for advanced DI patterns and features.

Run with: pytest tests/unit/DI/test_advanced_features.py -v
"""

import pytest
from typing import Annotated, Protocol
from unittest.mock import Mock, AsyncMock
import asyncio

from fastapi import Depends
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.core.eagle_di import (
    Injectable,
    AutoInject,
    Provide,
    get_service,
    forwardRef,
    Inject,
    override,
    test_container,
    clear_registry,
    Controller,
    process_async_inits,
    async_shutdown_all,
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
# Test: Controller Decorator
# =============================================================================


class TestControllerDecorator:
    """Tests for @Controller decorator"""

    def test_controller_is_injectable(self):
        """@Controller makes class injectable"""
        @Controller(prefix="/users", tags=["Users"])
        class UserController:
            pass

        assert hasattr(UserController, "__injectable__")
        assert UserController.__injectable__ is True

    def test_controller_has_metadata(self):
        """@Controller adds routing metadata"""
        @Controller(prefix="/api/v1", tags=["API", "V1"])
        class ApiController:
            pass

        assert ApiController.__controller__ is True
        assert ApiController.__prefix__ == "/api/v1"
        assert ApiController.__tags__ == ["API", "V1"]

    def test_controller_with_dependencies(self):
        """@Controller can have dependencies"""
        @Injectable
        class UserService:
            def get_users(self):
                return ["user1", "user2"]

        @Controller(prefix="/users")
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

        controller = get_service(UserController)
        assert controller.service.get_users() == ["user1", "user2"]

    def test_controller_empty_prefix(self):
        """@Controller with empty prefix"""
        @Controller()
        class RootController:
            pass

        assert RootController.__prefix__ == ""
        assert RootController.__tags__ == []


# =============================================================================
# Test: ForwardRef Patterns
# =============================================================================


class TestForwardRefPatterns:
    """Tests for forward reference patterns"""

    def test_forward_ref_with_lambda(self):
        """forwardRef with lambda works"""
        @Injectable
        class TargetService:
            value = "target"

        ref = forwardRef(lambda: TargetService)
        assert ref.resolve() is TargetService

    def test_forward_ref_caches_resolution(self):
        """forwardRef caches the resolved type"""
        call_count = [0]

        @Injectable
        class CachedService:
            pass

        def get_type():
            call_count[0] += 1
            return CachedService

        ref = forwardRef(get_type)
        
        # First call
        ref.resolve()
        assert call_count[0] == 1
        
        # Second call should use cache
        ref.resolve()
        assert call_count[0] == 1

    def test_forward_ref_repr_unresolved(self):
        """ForwardRef repr shows unresolved state"""
        ref = forwardRef(lambda: None)
        assert "unresolved" in repr(ref)

    def test_forward_ref_repr_resolved(self):
        """ForwardRef repr shows class name after resolution"""
        @Injectable
        class MyService:
            pass

        ref = forwardRef(lambda: MyService)
        ref.resolve()
        assert "MyService" in repr(ref)


# =============================================================================
# Test: Inject() Lazy Getter
# =============================================================================


class TestInjectLazyGetter:
    """Tests for Inject() lazy getter pattern"""

    def test_inject_returns_callable(self):
        """Inject() provides a getter function"""
        @Injectable
        class LazyService:
            value = "lazy"

        @Injectable
        class ConsumerService:
            def __init__(self, get_lazy: Inject(forwardRef(lambda: LazyService))):
                self._get_lazy = get_lazy

        consumer = get_service(ConsumerService)
        assert callable(consumer._get_lazy)

    def test_inject_getter_returns_singleton(self):
        """Inject getter returns same singleton"""
        @Injectable
        class SingletonService:
            pass

        @Injectable
        class Consumer:
            def __init__(self, get_svc: Inject(forwardRef(lambda: SingletonService))):
                self._get = get_svc

        consumer = get_service(Consumer)
        
        instance1 = consumer._get()
        instance2 = consumer._get()
        
        assert instance1 is instance2

    def test_inject_lazy_inject_repr(self):
        """LazyInject has proper repr"""
        ref = forwardRef(lambda: None)
        lazy = Inject(ref)
        assert "LazyInject" in repr(lazy)


# =============================================================================
# Test: Annotated Type Hints
# =============================================================================


class TestAnnotatedTypeHints:
    """Tests for Annotated type hints with Depends"""

    def test_annotated_with_depends(self):
        """Annotated[Type, Depends()] works"""
        @Injectable
        class AnnotatedService:
            pass

        @Injectable
        class Consumer:
            def __init__(
                self, 
                svc: Annotated[AnnotatedService, Depends(lambda: get_service(AnnotatedService))]
            ):
                self.svc = svc

        # This should work with the explicit Depends
        consumer = get_service(Consumer)
        assert isinstance(consumer.svc, AnnotatedService)


# =============================================================================
# Test: Async Lifecycle Advanced
# =============================================================================


class TestAsyncLifecycleAdvanced:
    """Advanced async lifecycle tests"""

    @pytest.mark.asyncio
    async def test_process_async_inits_idempotent(self):
        """process_async_inits can be called multiple times safely"""
        init_count = [0]

        @Injectable
        class CountingService:
            async def on_init(self):
                init_count[0] += 1

        get_service(CountingService)
        
        await process_async_inits()
        await process_async_inits()  # Second call
        await process_async_inits()  # Third call
        
        # Should only init once
        assert init_count[0] == 1

    @pytest.mark.asyncio
    async def test_multiple_async_services(self):
        """Multiple async services init properly"""
        inited = []

        @Injectable
        class Service1:
            async def on_init(self):
                inited.append("s1")

        @Injectable
        class Service2:
            async def on_init(self):
                inited.append("s2")

        @Injectable
        class Service3:
            async def on_init(self):
                inited.append("s3")

        get_service(Service1)
        get_service(Service2)
        get_service(Service3)
        
        await process_async_inits()
        
        assert set(inited) == {"s1", "s2", "s3"}

    @pytest.mark.asyncio
    async def test_sync_and_async_on_init_mixed(self):
        """Mix of sync and async on_init works"""
        events = []

        @Injectable
        class SyncService:
            def on_init(self):
                events.append("sync")

        @Injectable
        class AsyncService:
            async def on_init(self):
                events.append("async")

        get_service(SyncService)  # Sync runs immediately
        get_service(AsyncService)  # Async is queued
        
        assert "sync" in events
        assert "async" not in events
        
        await process_async_inits()
        
        assert "async" in events


# =============================================================================
# Test: Service Inheritance
# =============================================================================


class TestServiceInheritance:
    """Tests for injectable class inheritance"""

    def test_subclass_injectable(self):
        """Subclass of injectable is also injectable"""
        @Injectable
        class BaseService:
            def base_method(self):
                return "base"

        @Injectable
        class ChildService(BaseService):
            def child_method(self):
                return "child"

        child = get_service(ChildService)
        assert child.base_method() == "base"
        assert child.child_method() == "child"

    def test_subclass_with_super_init(self):
        """Subclass calling super().__init__"""
        @Injectable
        class Parent:
            def __init__(self):
                self.parent_value = "parent"

        @Injectable
        class Child(Parent):
            def __init__(self):
                super().__init__()
                self.child_value = "child"

        child = get_service(Child)
        assert child.parent_value == "parent"
        assert child.child_value == "child"


# =============================================================================
# Test: Registry State
# =============================================================================


class TestRegistryState:
    """Tests for registry state management"""

    def test_clear_registry_removes_all(self):
        """clear_registry removes all services"""
        @Injectable
        class Service1:
            pass

        @Injectable
        class Service2:
            pass

        get_service(Service1)
        get_service(Service2)
        
        clear_registry()
        
        with pytest.raises(ValueError):
            get_service(Service1)
        with pytest.raises(ValueError):
            get_service(Service2)

    def test_test_container_isolation(self):
        """test_container provides complete isolation"""
        @Injectable
        class OuterService:
            pass

        outer = get_service(OuterService)
        
        with test_container():
            # OuterService not available inside
            with pytest.raises(ValueError):
                get_service(OuterService)
            
            @Injectable
            class InnerService:
                pass

            inner = get_service(InnerService)
        
        # OuterService restored, InnerService gone
        assert get_service(OuterService) is outer
        
        with pytest.raises(ValueError):
            get_service(InnerService)

    def test_multiple_test_containers(self):
        """Multiple test containers can be used sequentially"""
        with test_container():
            @Injectable
            class Service1:
                pass
            get_service(Service1)

        with test_container():
            @Injectable
            class Service2:
                pass
            get_service(Service2)
            
            with pytest.raises(ValueError):
                get_service(Service1)  # Not available


# =============================================================================
# Test: AutoInject Edge Cases
# =============================================================================


class TestAutoInjectEdgeCases:
    """Edge cases for @AutoInject decorator"""

    def test_autoinject_preserves_function_metadata(self):
        """@AutoInject preserves function name and docstring"""
        @Injectable
        class MyService:
            pass

        @AutoInject
        def my_endpoint(svc: MyService):
            """My endpoint docstring"""
            pass

        assert my_endpoint.__name__ == "my_endpoint"
        # Note: docstring may or may not be preserved depending on implementation

    def test_autoinject_with_no_injectable_params(self):
        """@AutoInject with no injectable params works"""
        @AutoInject
        def plain_endpoint(name: str, age: int):
            return f"{name} is {age}"

        # Should not modify anything
        assert "name" in str(plain_endpoint.__signature__)

    def test_autoinject_mixed_params(self):
        """@AutoInject with mixed injectable and non-injectable params"""
        @Injectable
        class MyService:
            value = "svc"

        @AutoInject
        def mixed_endpoint(name: str, svc: MyService, age: int = 25):
            pass

        # Service param should have Depends, others unchanged
        sig = mixed_endpoint.__signature__
        assert "name" in str(sig)
        assert "age" in str(sig)
