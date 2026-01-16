"""
Unit Tests for FastAPI Dependency Injection Utility
=====================================================

Run with: pytest tests/test_injector.py -v
"""

import pytest
from unittest.mock import Mock

from app.core.eagle_di import (
    Injectable,
    Provide,
    get_service,
    forwardRef,
    Inject,
    override,
    test_container,
    clear_registry,
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
# Test: @Injectable Decorator
# =============================================================================


class TestInjectable:
    def test_registers_class(self):
        """@Injectable registers the class in the registry"""
        @Injectable
        class MyService:
            pass

        assert hasattr(MyService, "__injectable__")
        assert MyService.__injectable__ is True

    def test_singleton_scope(self):
        """Same instance is returned each time (singleton)"""
        @Injectable
        class SingletonService:
            pass

        s1 = get_service(SingletonService)
        s2 = get_service(SingletonService)

        assert s1 is s2

    def test_auto_inject_dependencies(self):
        """Dependencies are automatically injected via type hints"""
        @Injectable
        class Repository:
            def get_data(self):
                return "data"

        @Injectable
        class Service:
            def __init__(self, repo: Repository):
                self.repo = repo

        service = get_service(Service)

        assert isinstance(service.repo, Repository)
        assert service.repo.get_data() == "data"

    def test_nested_dependencies(self):
        """Nested dependencies are resolved correctly"""
        @Injectable
        class LevelC:
            value = "C"

        @Injectable
        class LevelB:
            def __init__(self, c: LevelC):
                self.c = c

        @Injectable
        class LevelA:
            def __init__(self, b: LevelB):
                self.b = b

        a = get_service(LevelA)

        assert isinstance(a.b, LevelB)
        assert isinstance(a.b.c, LevelC)
        assert a.b.c.value == "C"

    def test_raises_for_async_init(self):
        """Raises TypeError if __init__ is async"""
        with pytest.raises(TypeError, match="cannot be async"):
            @Injectable
            class BadService:
                async def __init__(self):
                    pass


# =============================================================================
# Test: get_service()
# =============================================================================


class TestGetService:
    def test_returns_singleton(self):
        """get_service returns the singleton instance"""
        @Injectable
        class MyService:
            pass

        instance = get_service(MyService)

        assert isinstance(instance, MyService)

    def test_raises_for_unregistered(self):
        """Raises ValueError for non-Injectable classes"""
        class NotInjectable:
            pass

        with pytest.raises(ValueError, match="is not @Injectable"):
            get_service(NotInjectable)


# =============================================================================
# Test: override() Context Manager
# =============================================================================


class TestOverride:
    def test_replaces_provider(self):
        """override() temporarily replaces the provider"""
        @Injectable
        class RealService:
            def get_value(self):
                return "real"

        mock_service = Mock()
        mock_service.get_value.return_value = "mocked"

        with override(RealService, mock_service):
            service = get_service(RealService)
            assert service.get_value() == "mocked"

    def test_restores_original(self):
        """Original provider is restored after context exits"""
        @Injectable
        class RealService:
            def get_value(self):
                return "real"

        mock_service = Mock()
        mock_service.get_value.return_value = "mocked"

        with override(RealService, mock_service):
            pass  # Do something with mock

        service = get_service(RealService)
        assert service.get_value() == "real"

    def test_returns_mock_instance(self):
        """override() returns the mock instance"""
        @Injectable
        class MyService:
            pass

        mock = Mock()

        with override(MyService, mock) as returned:
            assert returned is mock


# =============================================================================
# Test: test_container() Context Manager
# =============================================================================


class TestTestContainer:
    def test_creates_fresh_registry(self):
        """test_container provides a fresh registry"""
        @Injectable
        class OuterService:
            pass

        # Get instance before container
        outer_instance = get_service(OuterService)

        with test_container():
            # OuterService is not registered inside
            with pytest.raises(ValueError):
                get_service(OuterService)

            # Can register new service
            @Injectable
            class InnerService:
                pass

            inner = get_service(InnerService)
            assert isinstance(inner, InnerService)

        # After container, inner is gone, outer is restored
        assert get_service(OuterService) is outer_instance

    def test_supports_nesting(self):
        """Nested test_containers work correctly"""
        @Injectable
        class ServiceA:
            pass

        with test_container():
            @Injectable
            class ServiceB:
                pass

            with test_container():
                # Both A and B should not be registered here
                with pytest.raises(ValueError):
                    get_service(ServiceA)
                with pytest.raises(ValueError):
                    get_service(ServiceB)

            # ServiceB should be back
            get_service(ServiceB)


# =============================================================================
# Test: Lifecycle Hooks
# =============================================================================


class TestLifecycleHooks:
    def test_on_init_called(self):
        """on_init() is called after instantiation"""
        init_called = []

        @Injectable
        class ServiceWithInit:
            def on_init(self):
                init_called.append(True)

        get_service(ServiceWithInit)

        assert len(init_called) == 1

    def test_on_init_called_once_for_singleton(self):
        """on_init() is only called once for singletons"""
        init_count = []

        @Injectable
        class ServiceWithInit:
            def on_init(self):
                init_count.append(1)

        get_service(ServiceWithInit)
        get_service(ServiceWithInit)
        get_service(ServiceWithInit)

        assert len(init_count) == 1


# =============================================================================
# Test: Circular Dependencies
# =============================================================================


class TestCircularDependencies:
    def test_forward_ref_one_way(self):
        """forwardRef resolves one-way circular dependency"""
        @Injectable
        class ServiceA:
            value = "A"

        @Injectable
        class ServiceB:
            def __init__(self, a: forwardRef(lambda: ServiceA)):
                self.a = a

        b = get_service(ServiceB)

        assert isinstance(b.a, ServiceA)
        assert b.a.value == "A"

    def test_inject_returns_getter(self):
        """Inject(forwardRef()) returns a getter function"""
        @Injectable
        class ServiceA:
            value = "A"

        @Injectable
        class ServiceB:
            def __init__(self, get_a: Inject(forwardRef(lambda: ServiceA))):
                self._get_a = get_a

            def get_a_value(self):
                return self._get_a().value

        b = get_service(ServiceB)

        # _get_a is a callable
        assert callable(b._get_a)
        assert b.get_a_value() == "A"


# =============================================================================
# Test: Provide()
# =============================================================================


class TestProvide:
    def test_returns_depends(self):
        """Provide() returns a FastAPI Depends wrapper"""
        @Injectable
        class MyService:
            pass

        depends = Provide(MyService)

        # Should be a Depends instance
        assert hasattr(depends, "dependency")

    def test_raises_for_unregistered(self):
        """Raises ValueError for non-Injectable classes"""
        class NotInjectable:
            pass

        with pytest.raises(ValueError, match="is not @Injectable"):
            Provide(NotInjectable)


# =============================================================================
# Test: clear_registry()
# =============================================================================


class TestClearRegistry:
    def test_clears_all(self):
        """clear_registry() removes all registrations"""
        @Injectable
        class MyService:
            pass

        get_service(MyService)  # Create instance
        clear_registry()

        with pytest.raises(ValueError):
            get_service(MyService)
