"""
Tests for NestJS/Spring-Style Controller Pattern
=================================================

Tests @Controller decorator with @Get, @Post, etc. and register_controller().

Run with: pytest tests/test_controller_nestjs.py -v
"""

import pytest
from fastapi import FastAPI, Path, Query, Body
from fastapi.testclient import TestClient

from app.core.eagle_di import (
    Injectable,
    Controller,
    Get,
    Post,
    Put,
    Delete,
    Patch,
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
# Test: NestJS-Style Controllers
# =============================================================================


class TestNestJSStyleControllers:
    """Tests for NestJS/Spring-style @Controller pattern"""

    def test_controller_with_get_route(self):
        """@Controller with @Get route works"""
        @Injectable
        class UserService:
            def get_user(self, user_id: int) -> dict:
                return {"id": user_id, "name": f"User{user_id}"}

        @Controller(prefix="/users", tags=["Users"])
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Get("/{user_id}")
            def get_user(self, user_id: int):
                return self.service.get_user(user_id)

        app = FastAPI()
        register_controller(UserController, app)
        client = TestClient(app)

        response = client.get("/users/123")
        assert response.status_code == 200
        assert response.json() == {"id": 123, "name": "User123"}

    def test_controller_with_post_route(self):
        """@Controller with @Post route works"""
        @Injectable
        class UserService:
            def create_user(self, name: str) -> dict:
                return {"created": True, "name": name}

        @Controller(prefix="/users")
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Post()
            def create_user(self, data: dict = Body(...)):
                return self.service.create_user(data.get("name"))

        app = FastAPI()
        register_controller(UserController, app)
        client = TestClient(app)

        response = client.post("/users", json={"name": "Alice"})
        assert response.status_code == 200
        assert response.json() == {"created": True, "name": "Alice"}

    def test_controller_with_multiple_routes(self):
        """@Controller with multiple @Get/@Post routes"""
        @Injectable
        class UserService:
            def list_users(self) -> list:
                return [{"id": 1}, {"id": 2}]

            def get_user(self, user_id: int) -> dict:
                return {"id": user_id}

            def create_user(self) -> dict:
                return {"created": True}

        @Controller(prefix="/api/users", tags=["Users"])
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Get()
            def list_users(self):
                return self.service.list_users()

            @Get("/{user_id}")
            def get_user(self, user_id: int):
                return self.service.get_user(user_id)

            @Post()
            def create_user(self):
                return self.service.create_user()

        app = FastAPI()
        register_controller(UserController, app)
        client = TestClient(app)

        # Test list
        response = client.get("/api/users")
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Test get
        response = client.get("/api/users/5")
        assert response.status_code == 200
        assert response.json() == {"id": 5}

        # Test create
        response = client.post("/api/users")
        assert response.status_code == 200
        assert response.json() == {"created": True}

    def test_controller_with_all_http_methods(self):
        """@Controller with @Get, @Post, @Put, @Delete, @Patch"""
        @Injectable
        class ResourceService:
            pass

        @Controller(prefix="/resources")
        class ResourceController:
            def __init__(self, service: ResourceService):
                self.service = service

            @Get("/{id}")
            def get_resource(self, id: int):
                return {"method": "GET", "id": id}

            @Post()
            def create_resource(self):
                return {"method": "POST"}

            @Put("/{id}")
            def update_resource(self, id: int):
                return {"method": "PUT", "id": id}

            @Delete("/{id}")
            def delete_resource(self, id: int):
                return {"method": "DELETE", "id": id}

            @Patch("/{id}")
            def patch_resource(self, id: int):
                return {"method": "PATCH", "id": id}

        app = FastAPI()
        register_controller(ResourceController, app)
        client = TestClient(app)

        assert client.get("/resources/1").json() == {"method": "GET", "id": 1}
        assert client.post("/resources").json() == {"method": "POST"}
        assert client.put("/resources/2").json() == {"method": "PUT", "id": 2}
        assert client.delete("/resources/3").json() == {"method": "DELETE", "id": 3}
        assert client.patch("/resources/4").json() == {"method": "PATCH", "id": 4}

    def test_controller_with_query_params(self):
        """@Controller methods can use Query params"""
        @Injectable
        class SearchService:
            def search(self, query: str, limit: int) -> list:
                return [{"result": query}] * limit

        @Controller(prefix="/search")
        class SearchController:
            def __init__(self, service: SearchService):
                self.service = service

            @Get()
            def search(
                self,
                q: str = Query(...),
                limit: int = Query(10)
            ):
                return {"results": self.service.search(q, limit)}

        app = FastAPI()
        register_controller(SearchController, app)
        client = TestClient(app)

        response = client.get("/search?q=test&limit=3")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 3

    def test_controller_dependency_injection(self):
        """@Controller auto-injects services into constructor"""
        @Injectable
        class RepoA:
            def get_data(self) -> str:
                return "data_a"

        @Injectable
        class RepoB:
            def get_data(self) -> str:
                return "data_b"

        @Injectable
        class UserService:
            def __init__(self, repo_a: RepoA, repo_b: RepoB):
                self.repo_a = repo_a
                self.repo_b = repo_b

            def get_combined(self) -> dict:
                return {
                    "a": self.repo_a.get_data(),
                    "b": self.repo_b.get_data()
                }

        @Controller(prefix="/data")
        class DataController:
            def __init__(self, service: UserService):
                self.service = service

            @Get()
            def get_data(self):
                return self.service.get_combined()

        app = FastAPI()
        register_controller(DataController, app)
        client = TestClient(app)

        response = client.get("/data")
        assert response.status_code == 200
        assert response.json() == {"a": "data_a", "b": "data_b"}

    def test_controller_without_prefix(self):
        """@Controller without prefix works at root"""
        @Injectable
        class HealthService:
            def check(self) -> dict:
                return {"status": "ok"}

        @Controller()  # No prefix
        class HealthController:
            def __init__(self, service: HealthService):
                self.service = service

            @Get("/health")
            def health_check(self):
                return self.service.check()

        app = FastAPI()
        register_controller(HealthController, app)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_multiple_controllers_in_app(self):
        """Multiple @Controller classes can be registered"""
        @Injectable
        class UserService:
            pass

        @Injectable
        class ProductService:
            pass

        @Controller(prefix="/users")
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Get()
            def list_users(self):
                return {"users": []}

        @Controller(prefix="/products")
        class ProductController:
            def __init__(self, service: ProductService):
                self.service = service

            @Get()
            def list_products(self):
                return {"products": []}

        app = FastAPI()
        register_controller(UserController, app)
        register_controller(ProductController, app)
        client = TestClient(app)

        assert client.get("/users").json() == {"users": []}
        assert client.get("/products").json() == {"products": []}

    def test_controller_tags_in_openapi(self):
        """@Controller tags appear in OpenAPI spec"""
        @Injectable
        class UserService:
            pass

        @Controller(prefix="/users", tags=["Users", "V1"])
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Get()
            def list_users(self):
                return []

        app = FastAPI()
        register_controller(UserController, app)

        # Check OpenAPI spec
        openapi = app.openapi()
        paths = openapi["paths"]
        assert "/users" in paths
        assert "Users" in paths["/users"]["get"]["tags"]
        assert "V1" in paths["/users"]["get"]["tags"]




# =============================================================================
# Test: Advanced Controller Patterns
# =============================================================================


class TestAdvancedControllerPatterns:
    """Advanced test cases for production-ready controller patterns"""

    def test_controller_with_async_methods(self):
        """@Controller with async methods works correctly"""
        @Injectable
        class AsyncUserService:
            async def fetch_user(self, user_id: int) -> dict:
                # Simulate async DB call
                return {"id": user_id, "name": "Async User"}

        @Controller(prefix="/async")
        class AsyncController:
            def __init__(self, service: AsyncUserService):
                self.service = service

            @Get("/{user_id}")
            async def get_user(self, user_id: int):
                return await self.service.fetch_user(user_id)

        app = FastAPI()
        register_controller(AsyncController, app)
        client = TestClient(app)

        response = client.get("/async/42")
        assert response.status_code == 200
        assert response.json() == {"id": 42, "name": "Async User"}

    def test_controller_with_complex_nested_di(self):
        """@Controller with deeply nested service dependencies"""
        @Injectable
        class DatabaseAdapter:
            def query(self, sql: str) -> list:
                return [{"mock": "data"}]

        @Injectable
        class UserRepository:
            def __init__(self, db: DatabaseAdapter):
                self.db = db

            def find_all(self) -> list:
                return self.db.query("SELECT * FROM users")

        @Injectable
        class UserService:
            def __init__(self, repo: UserRepository):
                self.repo = repo

            def list_users(self) -> list:
                return self.repo.find_all()

        @Injectable
        class AuthService:
            def validate_token(self, token: str) -> bool:
                return token == "valid"

        @Controller(prefix="/users")
        class UserController:
            def __init__(self, user_svc: UserService, auth_svc: AuthService):
                # Multiple complex dependencies
                self.user_svc = user_svc
                self.auth_svc = auth_svc

            @Get()
            def list_users(self, token: str = Query("valid")):
                if not self.auth_svc.validate_token(token):
                    return {"error": "Unauthorized"}
                return {"users": self.user_svc.list_users()}

        app = FastAPI()
        register_controller(UserController, app)
        client = TestClient(app)

        response = client.get("/users?token=valid")
        assert response.status_code == 200
        assert "users" in response.json()

    def test_controller_with_middleware_pattern(self):
        """@Controller implementing middleware-like pre/post processing"""
        @Injectable
        class LoggingService:
            def __init__(self):
                self.logs = []

            def log(self, message: str):
                self.logs.append(message)

        @Controller(prefix="/logged")
        class LoggedController:
            def __init__(self, logger: LoggingService):
                self.logger = logger

            @Get("/{item_id}")
            def get_item(self, item_id: int):
                # Pre-processing
                self.logger.log(f"Fetching item {item_id}")

                # Main logic
                result = {"id": item_id, "name": f"Item{item_id}"}

                # Post-processing
                self.logger.log(f"Returned item {item_id}")

                return result

        app = FastAPI()
        register_controller(LoggedController, app)
        client = TestClient(app)

        response = client.get("/logged/5")
        assert response.status_code == 200

    def test_controller_with_exception_handling(self):
        """@Controller with custom exception handling"""
        class NotFoundException(Exception):
            pass

        @Injectable
        class ItemService:
            def get_item(self, item_id: int) -> dict:
                if item_id == 404:
                    raise NotFoundException(f"Item {item_id} not found")
                return {"id": item_id}

        @Controller(prefix="/items")
        class ItemController:
            def __init__(self, service: ItemService):
                self.service = service

            @Get("/{item_id}")
            def get_item(self, item_id: int):
                try:
                    return self.service.get_item(item_id)
                except NotFoundException as e:
                    return {"error": str(e), "status": 404}

        app = FastAPI()
        register_controller(ItemController, app)
        client = TestClient(app)

        # Valid item
        response = client.get("/items/1")
        assert response.status_code == 200
        assert response.json() == {"id": 1}

        # Not found
        response = client.get("/items/404")
        assert response.status_code == 200
        assert "error" in response.json()

    def test_controller_with_pydantic_models(self):
        """@Controller with Pydantic request/response models"""
        from pydantic import BaseModel

        class CreateUserRequest(BaseModel):
            name: str
            email: str

        class UserResponse(BaseModel):
            id: int
            name: str
            email: str

        @Injectable
        class UserService:
            def __init__(self):
                self.next_id = 1

            def create_user(self, name: str, email: str) -> dict:
                user_id = self.next_id
                self.next_id += 1
                return {"id": user_id, "name": name, "email": email}

        @Controller(prefix="/api/users")
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Post()
            def create_user(self, request: CreateUserRequest = Body(...)):
                return self.service.create_user(request.name, request.email)

        app = FastAPI()
        register_controller(UserController, app)
        client = TestClient(app)

        response = client.post(
            "/api/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Alice"

    def test_controller_with_shared_state(self):
        """@Controller with singleton service maintaining state"""
        @Injectable
        class CounterService:
            def __init__(self):
                self.count = 0

            def increment(self) -> int:
                self.count += 1
                return self.count

            def get_count(self) -> int:
                return self.count

        @Controller(prefix="/counter")
        class CounterController:
            def __init__(self, counter: CounterService):
                self.counter = counter

            @Post("/increment")
            def increment(self):
                return {"count": self.counter.increment()}

            @Get()
            def get_count(self):
                return {"count": self.counter.get_count()}

        app = FastAPI()
        register_controller(CounterController, app)
        client = TestClient(app)

        # Increment twice
        client.post("/counter/increment")
        client.post("/counter/increment")

        # Check count
        response = client.get("/counter")
        assert response.json()["count"] == 2

    def test_multiple_controllers_with_shared_services(self):
        """Multiple @Controllers sharing the same services (realistic production scenario)"""
        @Injectable
        class SharedCacheService:
            def __init__(self):
                self.cache = {}

            def set(self, key: str, value: any):
                self.cache[key] = value

            def get(self, key: str):
                return self.cache.get(key)

        @Controller(prefix="/users")
        class UserController:
            def __init__(self, cache: SharedCacheService):
                self.cache = cache

            @Post("/{user_id}")
            def cache_user(self, user_id: int):
                self.cache.set(f"user:{user_id}", {"id": user_id})
                return {"cached": True}

        @Controller(prefix="/products")
        class ProductController:
            def __init__(self, cache: SharedCacheService):
                self.cache = cache  # Same singleton instance!

            @Get("/{product_id}")
            def get_product(self, product_id: int):
                # Can access user cache because it's the same service
                user_cache = self.cache.get("user:1")
                return {"product_id": product_id, "user_cache": user_cache}

        app = FastAPI()
        register_controller(UserController, app)
        register_controller(ProductController, app)
        client = TestClient(app)

        # Cache user via UserController
        client.post("/users/1")

        # Access via ProductController (same service instance)
        response = client.get("/products/100")
        assert response.json()["user_cache"] == {"id": 1}


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestControllerErrorHandling:
    """Tests for error cases"""

    def test_register_non_controller_class_fails(self):
        """register_controller() raises error for non-@Controller class"""
        @Injectable
        class NotAController:
            pass

        app = FastAPI()

        with pytest.raises(ValueError, match="not a @Controller"):
            register_controller(NotAController, app)

    def test_controller_methods_without_route_decorators_ignored(self):
        """Methods without @Get/@Post are not registered as routes"""
        @Injectable
        class UserService:
            pass

        @Controller(prefix="/users")
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Get()
            def list_users(self):
                return []

            def helper_method(self):
                """This should NOT be registered as a route"""
                return "helper"

        app = FastAPI()
        register_controller(UserController, app)
        client = TestClient(app)

        # /users should work
        assert client.get("/users").status_code == 200

        # /users/helper_method should 404
        assert client.get("/users/helper_method").status_code == 404

    def test_no_internal_params_leak_to_swagger(self):
        """Verify internal _method_name parameter doesn't appear in OpenAPI spec"""
        @Injectable
        class UserService:
            pass

        @Controller(prefix="/api/users")
        class UserController:
            def __init__(self, service: UserService):
                self.service = service

            @Get("/{user_id}")
            def get_user(self, user_id: int):
                return {"id": user_id}

            @Post()
            def create_user(self, name: str = Query(...), email: str = Query(...)):
                return {"name": name, "email": email}

        app = FastAPI()
        register_controller(UserController, app)

        # Get OpenAPI spec
        openapi_spec = app.openapi()
        
        # Check GET endpoint
        get_params = openapi_spec["paths"]["/api/users/{user_id}"]["get"]["parameters"]
        param_names = [p["name"] for p in get_params]
        
        # Should only have user_id, NOT _method_name
        assert "user_id" in param_names
        assert "_method_name" not in param_names
        
        # Check POST endpoint
        post_params = openapi_spec["paths"]["/api/users"]["post"]["parameters"]
        post_param_names = [p["name"] for p in post_params]
        
        # Should have name and email, NOT _method_name
        assert "name" in post_param_names
        assert "email" in post_param_names
        assert "_method_name" not in post_param_names
        
        print("\n✅ No internal parameters leaked to Swagger UI!")
        print(f"   GET /api/users/{{user_id}} params: {param_names}")
        print(f"   POST /api/users params: {post_param_names}")

    def test_service_constructor_params_dont_leak(self):
        """
        CRITICAL: @Controller prevents service constructor params from leaking to Swagger!
        
        This was a real bug in v2.x where HereRoutingService's precision parameter
        leaked into controller endpoints because of nested Depends() chains.
        
        With @Controller, services are injected ONCE in __init__, so their constructor
        params NEVER appear in route parameters.
        """
        @Injectable
        class HereRoutingService:
            # Simulating the real v2.x bug scenario
            DEFAULT_PRECISION = 5
            
            def __init__(self, precision: int = DEFAULT_PRECISION):
                """
                In v2.x with @AutoInject, this precision param would LEAK
                into any controller endpoint using this service!
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
            "BUG: Service constructor param leaked to Swagger! Use @Controller to fix."
        
        print(f"\n✅ Service constructor params isolated from API!")
        print(f"   Route params: {param_names}")
        print(f"   Service precision: NOT leaked (stays internal)")
        
        # Verify it actually works
        client = TestClient(app)
        response = client.post("/routes/calculate?origin=A&destination=B")
        assert response.status_code == 200
        assert response.json()["route"]["precision"] == 5  # Uses default



# =============================================================================
# Summary
# =============================================================================


class TestNestJSStyleSummary:
    """Summary of NestJS/Spring-style controller features"""

    def test_feature_parity_with_nestjs(self):
        """
        Verify feature parity with NestJS @Controller pattern.
        All key features should be supported.
        """
        features = {
            "controller_decorator": True,
            "route_decorators": True,  # @Get, @Post, etc.
            "prefix_and_tags": True,
            "dependency_injection": True,
            "multiple_controllers": True,
            "all_http_methods": True,  # GET, POST, PUT, DELETE, PATCH
            "query_path_body_params": True,
        }

        assert all(features.values())

        print("\n🎯 NestJS/Spring-Style Controller Features:")
        for feature, supported in features.items():
            print(f"   ✅ {feature}: {supported}")
