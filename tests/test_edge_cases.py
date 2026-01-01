"""
Edge Cases and Error Handling Tests for DI Framework
=====================================================

Tests for boundary conditions, error scenarios, and edge cases.

Run with: pytest tests/unit/DI/test_edge_cases.py -v
"""

import pytest
from unittest.mock import Mock, patch
import threading
import time

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
# Test: Edge Cases for @Injectable
# =============================================================================


class TestInjectableEdgeCases:
    """Edge cases for @Injectable decorator"""

    def test_injectable_with_no_init(self):
        """Class with no __init__ should work"""
        @Injectable
        class NoInitService:
            value = "default"

        service = get_service(NoInitService)
        assert service.value == "default"

    def test_injectable_with_empty_init(self):
        """Class with empty __init__ should work"""
        @Injectable
        class EmptyInitService:
            def __init__(self):
                pass

        service = get_service(EmptyInitService)
        assert isinstance(service, EmptyInitService)

    def test_injectable_with_default_params(self):
        """Class with default params should use defaults"""
        @Injectable
        class DefaultParamsService:
            def __init__(self, value: str = "default", count: int = 10):
                self.value = value
                self.count = count

        service = get_service(DefaultParamsService)
        assert service.value == "default"
        assert service.count == 10

    def test_injectable_with_class_attributes(self):
        """Class attributes should be preserved"""
        @Injectable
        class AttributeService:
            class_attr = "class_value"
            
            def __init__(self):
                self.instance_attr = "instance_value"

        service = get_service(AttributeService)
        assert service.class_attr == "class_value"
        assert service.instance_attr == "instance_value"

    def test_injectable_with_property(self):
        """Properties should work on injectable classes"""
        @Injectable
        class PropertyService:
            def __init__(self):
                self._value = 0
            
            @property
            def value(self):
                return self._value
            
            @value.setter
            def value(self, v):
                self._value = v

        service = get_service(PropertyService)
        service.value = 42
        assert service.value == 42

    def test_injectable_with_staticmethod(self):
        """Static methods should work"""
        @Injectable
        class StaticService:
            @staticmethod
            def static_method():
                return "static"

        service = get_service(StaticService)
        assert service.static_method() == "static"

    def test_injectable_with_classmethod(self):
        """Class methods should work"""
        @Injectable
        class ClassMethodService:
            counter = 0
            
            @classmethod
            def increment(cls):
                cls.counter += 1
                return cls.counter

        service = get_service(ClassMethodService)
        assert service.increment() == 1
        assert service.increment() == 2


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error scenarios"""

    def test_get_service_unregistered_class(self):
        """get_service raises for unregistered class"""
        class NotRegistered:
            pass

        with pytest.raises(ValueError, match="is not @Injectable"):
            get_service(NotRegistered)

    def test_provide_unregistered_class(self):
        """Provide raises for unregistered class"""
        class NotRegistered:
            pass

        with pytest.raises(ValueError, match="is not @Injectable"):
            Provide(NotRegistered)

    def test_inject_without_forward_ref(self):
        """Inject() requires forwardRef()"""
        with pytest.raises(TypeError, match="requires forwardRef"):
            Inject("not a forward ref")

    def test_inject_with_wrong_type(self):
        """Inject() with wrong type raises TypeError"""
        with pytest.raises(TypeError):
            Inject(123)

    def test_async_init_rejected(self):
        """async __init__ should raise TypeError"""
        with pytest.raises(TypeError, match="cannot be async"):
            @Injectable
            class AsyncInitService:
                async def __init__(self):
                    pass


# =============================================================================
# Test: Thread Safety
# =============================================================================


class TestThreadSafety:
    """Tests for thread-safe singleton creation"""

    def test_concurrent_get_service_same_instance(self):
        """Concurrent calls should return same singleton"""
        @Injectable
        class ThreadSafeService:
            def __init__(self):
                self.created_at = time.time()

        instances = []
        errors = []

        def get_instance():
            try:
                instances.append(get_service(ThreadSafeService))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(instances) == 10
        # All should be the same instance
        assert all(i is instances[0] for i in instances)

    def test_concurrent_different_services(self):
        """Concurrent creation of different services"""
        @Injectable
        class ServiceA:
            pass

        @Injectable
        class ServiceB:
            pass

        @Injectable
        class ServiceC:
            pass

        results = {"a": [], "b": [], "c": []}

        def get_a():
            results["a"].append(get_service(ServiceA))

        def get_b():
            results["b"].append(get_service(ServiceB))

        def get_c():
            results["c"].append(get_service(ServiceC))

        threads = []
        for _ in range(5):
            threads.extend([
                threading.Thread(target=get_a),
                threading.Thread(target=get_b),
                threading.Thread(target=get_c),
            ])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results["a"]) == 5
        assert len(results["b"]) == 5
        assert len(results["c"]) == 5
        assert all(i is results["a"][0] for i in results["a"])
        assert all(i is results["b"][0] for i in results["b"])
        assert all(i is results["c"][0] for i in results["c"])


# =============================================================================
# Test: Override Edge Cases
# =============================================================================


class TestOverrideEdgeCases:
    """Edge cases for override context manager"""

    def test_override_with_none(self):
        """Override with None should work"""
        @Injectable
        class MyService:
            value = "real"

        with override(MyService, None):
            assert get_service(MyService) is None

    def test_nested_override(self):
        """Nested overrides should work correctly"""
        @Injectable
        class MyService:
            value = "real"

        mock1 = Mock()
        mock1.value = "mock1"
        mock2 = Mock()
        mock2.value = "mock2"

        with override(MyService, mock1):
            assert get_service(MyService).value == "mock1"
            
            with override(MyService, mock2):
                assert get_service(MyService).value == "mock2"
            
            # Back to mock1
            assert get_service(MyService).value == "mock1"

        # Back to real
        assert get_service(MyService).value == "real"

    def test_override_unregistered_service(self):
        """Override of unregistered service should still work"""
        class NotRegistered:
            pass

        mock = Mock()
        
        # This should not raise, just set up the mock
        with override(NotRegistered, mock):
            # The mock is now "registered"
            pass


# =============================================================================
# Test: Dependency Chain Edge Cases  
# =============================================================================


class TestDependencyChainEdgeCases:
    """Edge cases for dependency resolution"""

    def test_diamond_dependency(self):
        """Diamond dependency pattern should work"""
        #     A
        #    / \
        #   B   C
        #    \ /
        #     D
        @Injectable
        class D:
            value = "D"

        @Injectable
        class B:
            def __init__(self, d: D):
                self.d = d

        @Injectable
        class C:
            def __init__(self, d: D):
                self.d = d

        @Injectable
        class A:
            def __init__(self, b: B, c: C):
                self.b = b
                self.c = c

        a = get_service(A)
        
        # B and C should share the same D instance
        assert a.b.d is a.c.d

    def test_wide_dependency(self):
        """Service with many dependencies"""
        @Injectable
        class Dep1:
            pass

        @Injectable
        class Dep2:
            pass

        @Injectable
        class Dep3:
            pass

        @Injectable
        class Dep4:
            pass

        @Injectable
        class Dep5:
            pass

        @Injectable
        class WideService:
            def __init__(self, d1: Dep1, d2: Dep2, d3: Dep3, d4: Dep4, d5: Dep5):
                self.deps = [d1, d2, d3, d4, d5]

        service = get_service(WideService)
        assert len(service.deps) == 5
        assert all(d is not None for d in service.deps)

    def test_self_contained_service(self):
        """Service with no dependencies should resolve instantly"""
        @Injectable
        class SelfContained:
            def __init__(self):
                self.value = "standalone"

        service = get_service(SelfContained)
        assert service.value == "standalone"
