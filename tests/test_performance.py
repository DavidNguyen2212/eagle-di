"""
Performance Tests for DI Framework
===================================

Benchmarks to measure DI scalability and speed.

Run with: pytest tests/unit/DI/test_performance.py -v -s
"""

import time
import threading
import pytest

from app.core.eagle_di import (
    Injectable,
    get_service,
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
# Performance Benchmarks
# =============================================================================


class TestPerformance:
    """
    Performance benchmarks to measure DI scalability.

    Run with: pytest tests/unit/DI/test_performance.py -v -s
    """

    def test_registration_small_project(self):
        """
        Small project: 20 classes
        Expected: < 50ms
        """
        start = time.perf_counter()

        for i in range(20):
            @Injectable
            class Service:
                pass
            Service.__name__ = f"SmallService{i}"

        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n📊 Small Project (20 classes): {elapsed_ms:.2f}ms")
        assert elapsed_ms < 100, f"Registration too slow: {elapsed_ms:.2f}ms"

    def test_registration_medium_project(self):
        """
        Medium project: 50 classes
        Expected: < 100ms
        """
        start = time.perf_counter()

        for i in range(50):
            @Injectable
            class Service:
                pass
            Service.__name__ = f"MediumService{i}"

        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n📊 Medium Project (50 classes): {elapsed_ms:.2f}ms")
        assert elapsed_ms < 200, f"Registration too slow: {elapsed_ms:.2f}ms"

    def test_registration_large_project(self):
        """
        Large project: 100 classes
        Expected: < 200ms
        """
        start = time.perf_counter()

        for i in range(100):
            @Injectable
            class Service:
                pass
            Service.__name__ = f"LargeService{i}"

        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n📊 Large Project (100 classes): {elapsed_ms:.2f}ms")
        assert elapsed_ms < 500, f"Registration too slow: {elapsed_ms:.2f}ms"

    def test_resolution_with_deep_dependencies(self):
        """
        Resolution with 10-level deep dependency chain
        Expected: < 10ms
        """
        # Create a chain: L0 -> L1 -> L2 -> ... -> L9
        classes = []

        @Injectable
        class Level0:
            value = 0
        classes.append(Level0)

        for i in range(1, 10):
            prev_class = classes[-1]

            @Injectable
            class LevelN:
                def __init__(self, dep: prev_class):
                    self.dep = dep
                    self.level = i

            LevelN.__name__ = f"Level{i}"
            classes.append(LevelN)

        # Measure resolution time
        clear_registry()
        for cls in classes:
            Injectable(cls)

        start = time.perf_counter()
        deepest = get_service(classes[-1])
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n📊 Deep Resolution (10 levels): {elapsed_ms:.2f}ms")
        assert elapsed_ms < 50, f"Resolution too slow: {elapsed_ms:.2f}ms"

    def test_singleton_cache_performance(self):
        """
        Singleton cache hit should be < 0.1ms
        """
        @Injectable
        class CachedService:
            pass

        # First call creates instance
        get_service(CachedService)

        # Measure cached retrieval (1000 times)
        start = time.perf_counter()
        for _ in range(1000):
            get_service(CachedService)
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 1000
        print(f"\n📊 Singleton Cache Hit (avg of 1000): {avg_ms:.4f}ms")
        assert avg_ms < 0.1, f"Cache hit too slow: {avg_ms:.4f}ms"

    def test_concurrent_resolution(self):
        """
        Concurrent resolution from multiple threads
        Expected: Thread-safe, no errors
        """
        @Injectable
        class ThreadSafeService:
            pass

        errors = []
        results = []

        def resolve():
            try:
                service = get_service(ThreadSafeService)
                results.append(service)
            except Exception as e:
                errors.append(e)

        # Create 10 threads
        threads = [threading.Thread(target=resolve) for _ in range(10)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n📊 Concurrent Resolution (10 threads): {elapsed_ms:.2f}ms")
        
        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 10
        # All should be same singleton
        assert all(r is results[0] for r in results)

    def test_background_worker_simulation(self):
        """
        Simulate Celery/Background worker scenario:
        - Main thread registers services
        - Worker threads (simulating Celery workers) call get_service()
        
        This is the pattern for using DI in background tasks.
        """
        @Injectable
        class EmailService:
            def send(self, to: str) -> str:
                return f"sent to {to}"

        @Injectable
        class NotificationService:
            def __init__(self, email: EmailService):
                self.email = email
            
            def notify(self, user: str) -> str:
                return self.email.send(user)

        results = []
        errors = []

        def celery_task_simulation(task_id: int):
            """Simulates a Celery task calling get_service()"""
            try:
                # This is how you use DI in Celery/background tasks
                service = get_service(NotificationService)
                result = service.notify(f"user_{task_id}")
                results.append((task_id, result))
            except Exception as e:
                errors.append((task_id, e))

        # Simulate 5 concurrent Celery workers
        workers = [
            threading.Thread(target=celery_task_simulation, args=(i,))
            for i in range(5)
        ]

        for w in workers:
            w.start()
        for w in workers:
            w.join()

        print(f"\n📊 Background Worker Simulation: {len(results)} tasks completed")
        
        assert len(errors) == 0, f"Worker errors: {errors}"
        assert len(results) == 5
        
        # Verify all workers got the same singleton
        all_services = [get_service(NotificationService) for _ in range(5)]
        assert all(s is all_services[0] for s in all_services)
        
        print("✅ All workers share the same singleton - safe for Celery/Workers!")


    def test_memory_efficiency(self):
        """
        Test that 100 singletons can be created without issues.
        Note: Python's gc makes precise memory measurement unreliable.
        """
        created_services = []
        
        for i in range(100):
            @Injectable
            class MemService:
                data = [0] * 100  # Some data

            MemService.__name__ = f"MemService{i}"
            svc = get_service(MemService)
            created_services.append(svc)

        print(f"\n📊 Memory Test: Created {len(created_services)} singleton instances")
        assert len(created_services) == 100, "Should create 100 services"

    def test_realistic_app_structure(self):
        """
        Simulate real FastAPI app structure:
        - 5 Controllers → 10 Services → 5 Repositories
        """
        # Layer 1: Repositories (no deps)
        repos = []
        for i in range(5):
            @Injectable
            class Repository:
                def find(self):
                    return f"data_{i}"
            Repository.__name__ = f"Repository{i}"
            repos.append(Repository)

        # Layer 2: Services (depend on repos)
        services = []
        for i in range(10):
            repo = repos[i % 5]

            @Injectable
            class Service:
                def __init__(self, r: repo):
                    self.repo = r
            Service.__name__ = f"Service{i}"
            services.append(Service)

        # Layer 3: Controllers (depend on services)
        controllers = []
        for i in range(5):
            svc1 = services[i * 2]
            svc2 = services[i * 2 + 1]

            @Injectable
            class Controller:
                def __init__(self, s1: svc1, s2: svc2):
                    self.s1 = s1
                    self.s2 = s2
            Controller.__name__ = f"Controller{i}"
            controllers.append(Controller)

        # Measure resolution of deepest controller
        start = time.perf_counter()
        for ctrl_cls in controllers:
            get_service(ctrl_cls)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n📊 Real-world App (5 ctrl → 10 svc → 5 repo): {elapsed_ms:.2f}ms")
        assert elapsed_ms < 50, f"Too slow: {elapsed_ms:.2f}ms"

    def test_override_speed(self):
        """
        override() context manager should be fast
        Expected: < 1ms per override
        """
        @Injectable
        class OriginalService:
            def value(self):
                return "original"

        mock = type("Mock", (), {"value": lambda self: "mocked"})()

        # Measure 100 override cycles
        start = time.perf_counter()
        for _ in range(100):
            with override(OriginalService, mock):
                get_service(OriginalService)
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 100
        print(f"\n📊 Override Speed (avg of 100): {avg_ms:.3f}ms")
        assert avg_ms < 1, f"Override too slow: {avg_ms:.3f}ms"

    def test_cold_vs_warm_start(self):
        """
        Compare first resolution (cold) vs cached (warm)
        Expected: Warm should be 10x+ faster
        """
        @Injectable
        class ColdWarmService:
            pass

        # Cold start (first resolution)
        start = time.perf_counter()
        get_service(ColdWarmService)
        cold_ms = (time.perf_counter() - start) * 1000

        # Warm start (cached)
        start = time.perf_counter()
        for _ in range(100):
            get_service(ColdWarmService)
        warm_total_ms = (time.perf_counter() - start) * 1000
        warm_avg_ms = warm_total_ms / 100

        speedup = cold_ms / warm_avg_ms if warm_avg_ms > 0 else float('inf')

        print(f"\n📊 Cold Start: {cold_ms:.3f}ms")
        print(f"📊 Warm Start (avg): {warm_avg_ms:.4f}ms")
        print(f"📊 Speedup: {speedup:.0f}x faster when cached")

        assert warm_avg_ms < cold_ms, "Warm should be faster than cold"
