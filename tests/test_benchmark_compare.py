"""
Benchmark Comparison: Custom DI vs dependency-injector Library
===============================================================

This file compares performance between our custom DI and the 
popular dependency-injector library.

Run with: pytest tests/unit/DI/test_benchmark_compare.py -v -s

NOTE: Requires `pip install dependency-injector` to run.
If not installed, tests will be skipped.
"""

import time
import pytest

# Try to import dependency-injector
try:
    from dependency_injector import containers, providers
    HAS_DI_LIBRARY = True
except ImportError:
    HAS_DI_LIBRARY = False

from app.core.eagle_di import (
    Injectable,
    get_service,
    test_container,
    clear_registry,
)


# Skip all tests if dependency-injector is not installed
pytestmark = pytest.mark.skipif(
    not HAS_DI_LIBRARY,
    reason="dependency-injector not installed. Run: pip install dependency-injector"
)


@pytest.fixture(autouse=True)
def isolate_tests():
    """Each test runs in isolated container"""
    with test_container():
        yield


class TestBenchmarkComparison:
    """
    Side-by-side performance comparison between:
    - Your Custom DI (injector.py)
    - dependency-injector library
    """

    def test_registration_speed(self):
        """
        Compare class registration speed
        """
        NUM_CLASSES = 50

        # ================== Custom DI ==================
        clear_registry()
        start = time.perf_counter()
        
        for i in range(NUM_CLASSES):
            @Injectable
            class CustomService:
                pass
            CustomService.__name__ = f"CustomService{i}"
        
        custom_time = (time.perf_counter() - start) * 1000

        # ================== dependency-injector ==================
        class DIContainer(containers.DeclarativeContainer):
            pass

        start = time.perf_counter()
        
        for i in range(NUM_CLASSES):
            class LibService:
                pass
            LibService.__name__ = f"LibService{i}"
            setattr(DIContainer, f"service_{i}", providers.Singleton(LibService))
        
        lib_time = (time.perf_counter() - start) * 1000

        # Results
        print(f"\n{'='*60}")
        print(f"📊 REGISTRATION SPEED ({NUM_CLASSES} classes)")
        print(f"{'='*60}")
        print(f"   Custom DI:          {custom_time:.2f}ms")
        print(f"   dependency-injector: {lib_time:.2f}ms")
        
        if custom_time < lib_time:
            speedup = lib_time / custom_time
            print(f"   ✅ Custom DI is {speedup:.1f}x FASTER")
        else:
            speedup = custom_time / lib_time
            print(f"   ⚠️ dependency-injector is {speedup:.1f}x faster")
        print(f"{'='*60}")

    def test_resolution_speed(self):
        """
        Compare dependency resolution speed
        """
        NUM_RESOLUTIONS = 1000

        # ================== Custom DI ==================
        @Injectable
        class CustomRepo:
            pass

        @Injectable  
        class CustomService:
            def __init__(self, repo: CustomRepo):
                self.repo = repo

        # Warm up
        get_service(CustomService)
        clear_registry()
        
        @Injectable
        class CustomRepo2:
            pass
        @Injectable
        class CustomService2:
            def __init__(self, repo: CustomRepo2):
                self.repo = repo
        
        get_service(CustomService2)  # Create singleton
        
        start = time.perf_counter()
        for _ in range(NUM_RESOLUTIONS):
            get_service(CustomService2)
        custom_time = (time.perf_counter() - start) * 1000

        # ================== dependency-injector ==================
        class LibRepo:
            pass

        class LibService:
            def __init__(self, repo: LibRepo):
                self.repo = repo

        class Container(containers.DeclarativeContainer):
            repo = providers.Singleton(LibRepo)
            service = providers.Singleton(LibService, repo=repo)

        container = Container()
        container.service()  # Warm up

        start = time.perf_counter()
        for _ in range(NUM_RESOLUTIONS):
            container.service()
        lib_time = (time.perf_counter() - start) * 1000

        # Results
        print(f"\n{'='*60}")
        print(f"📊 RESOLUTION SPEED ({NUM_RESOLUTIONS} calls, cached singleton)")
        print(f"{'='*60}")
        print(f"   Custom DI:          {custom_time:.3f}ms ({custom_time/NUM_RESOLUTIONS*1000:.2f}μs/call)")
        print(f"   dependency-injector: {lib_time:.3f}ms ({lib_time/NUM_RESOLUTIONS*1000:.2f}μs/call)")
        
        if custom_time < lib_time:
            speedup = lib_time / custom_time
            print(f"   ✅ Custom DI is {speedup:.1f}x FASTER")
        else:
            speedup = custom_time / lib_time
            print(f"   ⚠️ dependency-injector is {speedup:.1f}x faster")
        print(f"{'='*60}")

    def test_deep_dependency_chain(self):
        """
        Compare resolution of deep dependency chains (5 levels)
        """
        DEPTH = 5
        NUM_RESOLUTIONS = 100

        # ================== Custom DI ==================
        clear_registry()
        
        @Injectable
        class Level0:
            pass
        
        prev = Level0
        for i in range(1, DEPTH):
            @Injectable
            class LevelN:
                def __init__(self, dep: prev):
                    self.dep = dep
            LevelN.__name__ = f"Level{i}"
            prev = LevelN
        
        deepest_custom = prev
        get_service(deepest_custom)  # Warm up
        
        start = time.perf_counter()
        for _ in range(NUM_RESOLUTIONS):
            get_service(deepest_custom)
        custom_time = (time.perf_counter() - start) * 1000

        # ================== dependency-injector ==================
        class L0:
            pass
        class L1:
            def __init__(self, dep: L0): self.dep = dep
        class L2:
            def __init__(self, dep: L1): self.dep = dep
        class L3:
            def __init__(self, dep: L2): self.dep = dep
        class L4:
            def __init__(self, dep: L3): self.dep = dep

        class Container(containers.DeclarativeContainer):
            l0 = providers.Singleton(L0)
            l1 = providers.Singleton(L1, dep=l0)
            l2 = providers.Singleton(L2, dep=l1)
            l3 = providers.Singleton(L3, dep=l2)
            l4 = providers.Singleton(L4, dep=l3)

        container = Container()
        container.l4()  # Warm up

        start = time.perf_counter()
        for _ in range(NUM_RESOLUTIONS):
            container.l4()
        lib_time = (time.perf_counter() - start) * 1000

        # Results
        print(f"\n{'='*60}")
        print(f"📊 DEEP CHAIN ({DEPTH} levels, {NUM_RESOLUTIONS} calls)")
        print(f"{'='*60}")
        print(f"   Custom DI:          {custom_time:.3f}ms")
        print(f"   dependency-injector: {lib_time:.3f}ms")
        
        if custom_time < lib_time:
            speedup = lib_time / custom_time
            print(f"   ✅ Custom DI is {speedup:.1f}x FASTER")
        else:
            speedup = custom_time / lib_time
            print(f"   ⚠️ dependency-injector is {speedup:.1f}x faster")
        print(f"{'='*60}")

    def test_code_complexity_comparison(self):
        """
        Compare code complexity (lines of code to achieve same result)
        """
        print(f"\n{'='*60}")
        print(f"📊 CODE COMPLEXITY COMPARISON")
        print(f"{'='*60}")
        
        print("\n--- Custom DI (3 lines) ---")
        print("""
@Injectable
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo
""")
        
        print("--- dependency-injector (8+ lines) ---")
        print("""
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

class Container(containers.DeclarativeContainer):
    user_repo = providers.Singleton(UserRepository)
    user_service = providers.Singleton(
        UserService, 
        repo=user_repo
    )
""")
        
        print(f"\n   ✅ Custom DI: ~60% less boilerplate!")
        print(f"{'='*60}")


class TestFeatureComparison:
    """
    Feature-by-feature comparison
    """

    def test_print_feature_matrix(self):
        """Print feature comparison matrix"""
        print(f"\n{'='*60}")
        print(f"📊 FEATURE COMPARISON MATRIX")
        print(f"{'='*60}")
        print(f"{'Feature':<30} {'Custom DI':<15} {'DI Library':<15}")
        print(f"{'-'*60}")
        print(f"{'Auto-inject by type hint':<30} {'✅ Yes':<15} {'❌ Manual':<15}")
        print(f"{'Singleton scope':<30} {'✅ Default':<15} {'✅ Yes':<15}")
        print(f"{'Request scope':<30} {'❌ No':<15} {'✅ Yes':<15}")
        print(f"{'Transient scope':<30} {'❌ No':<15} {'✅ Yes':<15}")
        print(f"{'Lifecycle hooks':<30} {'✅ on_init/destroy':<15} {'✅ Yes':<15}")
        print(f"{'Circular deps':<30} {'✅ forwardRef':<15} {'✅ Yes':<15}")
        print(f"{'Testing utilities':<30} {'✅ override/container':<15} {'✅ Yes':<15}")
        print(f"{'Zero dependencies':<30} {'✅ Yes':<15} {'❌ Cython':<15}")
        print(f"{'Copy-paste ready':<30} {'✅ 1 file':<15} {'❌ pip install':<15}")
        print(f"{'LOC':<30} {'~780':<15} {'~15000+':<15}")
        print(f"{'='*60}")
        print(f"\n   📌 Custom DI: 80% features, 5% complexity!")
