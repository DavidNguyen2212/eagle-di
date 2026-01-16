"""
Tests for Swagger/OpenAPI Spec Compatibility
=============================================

Ensures that internal DI parameters don't leak into Swagger UI.

This was a real bug in v2.x where service constructor parameters (like
HereRoutingService's `precision` param) leaked into controller endpoints
because of nested Depends() chains.

Both InjectableRouter and @Controller patterns should prevent this leak.

Run with: pytest tests/test_swagger_compatible.py -v
"""

import pytest
from fastapi import FastAPI, Query, Body, Path
from fastapi.testclient import TestClient

from app.core.eagle_di import (
    Injectable,
    InjectableRouter,
    Controller,
    Get,
    Post,
    register_controller,
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
# Test: InjectableRouter Swagger Compatibility
# =============================================================================


class TestInjectableRouterSwaggerCompatibility:
    """Verify InjectableRouter doesn't leak service constructor params to Swagger"""

    def test_service_constructor_params_dont_leak(self):
        """
        CRITICAL: InjectableRouter prevents service constructor params from leaking!
        
        Simulates the real v2.x HereRoutingService bug where precision parameter
        leaked into controller endpoints.
        """
        @Injectable
        class HereRoutingService:
            DEFAULT_PRECISION = 5
            
            def __init__(self, precision: int = DEFAULT_PRECISION):
                """
                This precision param should NOT appear in Swagger
                for any endpoint using this service!
                """
                self.precision = precision
            
            def calculate_route(self) -> dict:
                return {"precision": self.precision}

        router = InjectableRouter(prefix="/routes")

        @router.post("/calculate")
        def calculate_route(
            origin: str = Query(...),
            destination: str = Query(...),
            routing_svc: HereRoutingService = None  # DI-injected
        ):
            """
            IMPORTANT: Only origin and destination should appear in Swagger,
            NOT precision from HereRoutingService.__init__!
            """
            return {
                "origin": origin,
                "destination": destination,
                "route": routing_svc.calculate_route()
            }

        app = FastAPI()
        app.include_router(router)
        
        # Get OpenAPI spec
        openapi_spec = app.openapi()
        post_params = openapi_spec["paths"]["/routes/calculate"]["post"]["parameters"]
        param_names = [p["name"] for p in post_params]
        
        # ✅ Should ONLY have origin and destination
        assert "origin" in param_names
        assert "destination" in param_names
        
        # ✅ Should NOT have precision from service constructor!
        assert "precision" not in param_names, \
            "BUG: Service constructor param leaked to Swagger!"
        
        # ✅ Should NOT have routing_svc (it's injected)
        assert "routing_svc" not in param_names
        
        print(f"\n✅ [InjectableRouter] Service constructor params isolated!")
        print(f"   API params: {param_names}")
        print(f"   Internal service: precision={HereRoutingService.DEFAULT_PRECISION}")
        
        # Verify it works
        client = TestClient(app)
        response = client.post("/routes/calculate?origin=A&destination=B")
        assert response.status_code == 200
        assert response.json()["route"]["precision"] == 5

    def test_multiple_services_with_constructor_params(self):
        """Complex scenario: Multiple services with constructor params"""
        @Injectable
        class DatabaseConfig:
            def __init__(self, pool_size: int = 10, timeout: int = 30):
                self.pool_size = pool_size
                self.timeout = timeout

        @Injectable
        class CacheConfig:
            def __init__(self, ttl: int = 300, max_size: int = 1000):
                self.ttl = ttl
                self.max_size = max_size

        @Injectable
        class UserService:
            def __init__(self, db_config: DatabaseConfig, cache_config: CacheConfig):
                self.db_config = db_config
                self.cache_config = cache_config
            
            def get_config(self) -> dict:
                return {
                    "db_pool": self.db_config.pool_size,
                    "cache_ttl": self.cache_config.ttl
                }

        router = InjectableRouter(prefix="/api")

        @router.get("/config")
        def get_config(service: UserService = None):
            """
            Should NOT expose: pool_size, timeout, ttl, max_size
            These are internal service configs!
            """
            return service.get_config()

        app = FastAPI()
        app.include_router(router)
        
        openapi_spec = app.openapi()
        
        # GET /api/config should have NO parameters
        get_params = openapi_spec["paths"]["/api/config"]["get"].get("parameters", [])
        param_names = [p["name"] for p in get_params]
        
        # ✅ Should NOT expose any service constructor params
        assert "pool_size" not in param_names
        assert "timeout" not in param_names
        assert "ttl" not in param_names
        assert "max_size" not in param_names
        assert "service" not in param_names
        
        print(f"\n✅ [InjectableRouter] Complex DI chain: NO leaks!")
        print(f"   API params: {param_names} (should be empty)")


# =============================================================================
# Test: Controller Swagger Compatibility
# =============================================================================


class TestControllerSwaggerCompatibility:
    """Verify @Controller doesn't leak service constructor params to Swagger"""

    def test_service_constructor_params_dont_leak(self):
        """
        CRITICAL: @Controller prevents service constructor params from leaking!
        
        Same scenario as InjectableRouter test but with @Controller pattern.
        """
        @Injectable
        class HereRoutingService:
            DEFAULT_PRECISION = 5
            
            def __init__(self, precision: int = DEFAULT_PRECISION):
                """
                This precision param should NOT appear in Swagger!
                """
                self.precision = precision
            
            def calculate_route(self) -> dict:
                return {"precision": self.precision}

        @Controller(prefix="/routes")
        class RouteController:
            def __init__(self, routing_svc: HereRoutingService):
                # Service injected ONCE in constructor
                self.routing_svc = routing_svc

            @Post("/calculate")
            def calculate_route(
                self, 
                origin: str = Query(...),
                destination: str = Query(...)
            ):
                """
                IMPORTANT: Only origin and destination should appear in Swagger,
                NOT precision from HereRoutingService.__init__!
                """
                return {
                    "origin": origin,
                    "destination": destination,
                    "route": self.routing_svc.calculate_route()
                }

        app = FastAPI()
        register_controller(RouteController, app)
        
        # Get OpenAPI spec
        openapi_spec = app.openapi()
        post_params = openapi_spec["paths"]["/routes/calculate"]["post"]["parameters"]
        param_names = [p["name"] for p in post_params]
        
        # ✅ Should ONLY have origin and destination
        assert "origin" in param_names
        assert "destination" in param_names
        
        # ✅ Should NOT have precision from service constructor!
        assert "precision" not in param_names, \
            "BUG: Service constructor param leaked to Swagger!"
        
        # ✅ Should NOT have _method_name (internal param)
        assert "_method_name" not in param_names
        
        print(f"\n✅ [@Controller] Service constructor params isolated!")
        print(f"   API params: {param_names}")
        print(f"   Internal service: precision={HereRoutingService.DEFAULT_PRECISION}")
        
        # Verify it works
        client = TestClient(app)
        response = client.post("/routes/calculate?origin=A&destination=B")
        assert response.status_code == 200
        assert response.json()["route"]["precision"] == 5

    def test_multiple_services_with_constructor_params(self):
        """Complex scenario: Multiple services with constructor params in controller"""
        @Injectable
        class DatabaseConfig:
            def __init__(self, pool_size: int = 10, timeout: int = 30):
                self.pool_size = pool_size
                self.timeout = timeout

        @Injectable
        class CacheConfig:
            def __init__(self, ttl: int = 300, max_size: int = 1000):
                self.ttl = ttl
                self.max_size = max_size

        @Injectable
        class UserService:
            def __init__(self, db_config: DatabaseConfig, cache_config: CacheConfig):
                self.db_config = db_config
                self.cache_config = cache_config
            
            def get_config(self) -> dict:
                return {
                    "db_pool": self.db_config.pool_size,
                    "cache_ttl": self.cache_config.ttl
                }

        @Controller(prefix="/api")
        class ConfigController:
            def __init__(self, service: UserService):
                self.service = service

            @Get("/config")
            def get_config(self):
                """
                Should NOT expose: pool_size, timeout, ttl, max_size
                These are internal service configs!
                """
                return self.service.get_config()

        app = FastAPI()
        register_controller(ConfigController, app)
        
        openapi_spec = app.openapi()
        
        # GET /api/config should have NO parameters
        get_params = openapi_spec["paths"]["/api/config"]["get"].get("parameters", [])
        param_names = [p["name"] for p in get_params]
        
        # ✅ Should NOT expose any service constructor params
        assert "pool_size" not in param_names
        assert "timeout" not in param_names
        assert "ttl" not in param_names
        assert "max_size" not in param_names
        assert "_method_name" not in param_names
        
        print(f"\n✅ [@Controller] Complex DI chain: NO leaks!")
        print(f"   API params: {param_names} (should be empty)")


# =============================================================================
# Test: Comparison Summary
# =============================================================================


class TestSwaggerCompatibilitySummary:
    """Summary test comparing both patterns"""

    def test_both_patterns_prevent_leaks(self):
        """
        Verify that BOTH InjectableRouter and @Controller prevent
        service constructor param leaks to Swagger.
        
        This is a critical feature for production APIs.
        """
        # Shared service with constructor param
        @Injectable
        class SharedService:
            def __init__(self, internal_config: int = 42):
                self.config = internal_config

        # Pattern 1: InjectableRouter
        router = InjectableRouter(prefix="/router")
        
        @router.get("/test")
        def router_endpoint(svc: SharedService = None):
            return {"config": svc.config}

        # Pattern 2: @Controller
        @Controller(prefix="/controller")
        class TestController:
            def __init__(self, svc: SharedService):
                self.svc = svc

            @Get("/test")
            def controller_endpoint(self):
                return {"config": self.svc.config}

        app = FastAPI()
        app.include_router(router)
        register_controller(TestController, app)
        
        openapi_spec = app.openapi()
        
        # Check router endpoint
        router_params = openapi_spec["paths"]["/router/test"]["get"].get("parameters", [])
        router_param_names = [p["name"] for p in router_params]
        
        # Check controller endpoint
        controller_params = openapi_spec["paths"]["/controller/test"]["get"].get("parameters", [])
        controller_param_names = [p["name"] for p in controller_params]
        
        # ✅ BOTH should have NO parameters
        assert "internal_config" not in router_param_names
        assert "internal_config" not in controller_param_names
        assert "svc" not in router_param_names
        assert "_method_name" not in controller_param_names
        
        print("\n🎯 Swagger Compatibility Summary:")
        print(f"   ✅ InjectableRouter: NO leaks (params: {router_param_names})")
        print(f"   ✅ @Controller: NO leaks (params: {controller_param_names})")
        print(f"   ✅ Both patterns are production-ready!")
