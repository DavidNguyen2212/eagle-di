"""
Comprehensive InjectableRouter Tests
=====================================

Tests specifically for the InjectableRouter functionality and auto-injection
without needing the @AutoInject decorator.

Run with: pytest tests/test_injectable_router.py -v
"""

import pytest
from fastapi import FastAPI, Query, Path, Body, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional

from app.core.eagle_di import (
    Injectable,
    InjectableRouter,
    test_container,
)


# =============================================================================
# Pydantic Models
# =============================================================================


class User(BaseModel):
    name: str
    email: str


class CreateUserRequest(BaseModel):
    name: str
    email: str
    age: Optional[int] = None


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def isolate_tests():
    """Each test runs in isolated container"""
    with test_container():
        yield


# =============================================================================
# Test: Basic InjectableRouter Functionality
# =============================================================================


class TestBasicAutoInjection:
    """Tests for basic auto-injection without @AutoInject decorator"""

    def test_simple_auto_injection(self):
        """InjectableRouter automatically injects services"""
        @Injectable
        class UserService:
            def get_user(self, id: int) -> dict:
                return {"id": id, "name": f"User{id}"}

        app = FastAPI()
        router = InjectableRouter()

        # NO @AutoInject decorator needed!
        @router.get("/users/{id}")
        def get_user(id: int, service: UserService):
            return service.get_user(id)

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/users/123")

        assert response.status_code == 200
        assert response.json() == {"id": 123, "name": "User123"}

    def test_auto_injection_with_path_params(self):
        """Auto-injection works alongside path parameters"""
        @Injectable
        class MessageService:
            def greet(self, name: str) -> str:
                return f"Hello, {name}!"

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/greet/{name}")
        def greet(name: str, service: MessageService):
            return {"greeting": service.greet(name)}

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/greet/Alice")

        assert response.status_code == 200
        assert response.json() == {"greeting": "Hello, Alice!"}

    def test_auto_injection_with_query_params(self):
        """Auto-injection works with query parameters"""
        @Injectable
        class SearchService:
            def search(self, query: str) -> list:
                return [f"Result for {query}"]

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/search")
        def search(q: str, service: SearchService):
            return {"results": service.search(q)}

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/search?q=test")

        assert response.status_code == 200
        assert response.json() == {"results": ["Result for test"]}

    def test_auto_injection_with_post_body(self):
        """Auto-injection works with POST request bodies"""
        @Injectable
        class UserService:
            def create_user(self, name: str, email: str) -> dict:
                return {"name": name, "email": email, "created": True}

        app = FastAPI()
        router = InjectableRouter()

        @router.post("/users")
        def create_user(user: CreateUserRequest, service: UserService):
            return service.create_user(user.name, user.email)

        app.include_router(router)
        client = TestClient(app)
        response = client.post("/users", json={
            "name": "Bob",
            "email": "bob@example.com"
        })

        assert response.status_code == 200
        assert response.json() == {
            "name": "Bob",
            "email": "bob@example.com",
            "created": True
        }


# =============================================================================
# Test: Multiple Services and Nested Dependencies
# =============================================================================


class TestMultipleServices:
    """Tests for multiple service injection and nested dependencies"""

    def test_multiple_services_auto_injected(self):
        """Multiple services can be auto-injected in same endpoint"""
        @Injectable
        class ServiceA:
            def get_a(self) -> str:
                return "A"

        @Injectable
        class ServiceB:
            def get_b(self) -> str:
                return "B"

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/multi")
        def multi(svc_a: ServiceA, svc_b: ServiceB, param: str = "default"):
            return {
                "a": svc_a.get_a(),
                "b": svc_b.get_b(),
                "param": param
            }

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/multi")

        assert response.status_code == 200
        assert response.json() == {"a": "A", "b": "B", "param": "default"}

    def test_nested_service_dependencies(self):
        """InjectableRouter works with nested service dependencies"""
        @Injectable
        class Repository:
            def get_data(self) -> str:
                return "data from repo"

        @Injectable
        class Service:
            def __init__(self, repo: Repository):
                self.repo = repo

            def process(self) -> str:
                return f"Processed: {self.repo.get_data()}"

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/process")
        def process(service: Service):
            return {"result": service.process()}

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/process")

        assert response.status_code == 200
        assert response.json() == {"result": "Processed: data from repo"}


# =============================================================================
# Test: Service Defaults (Hidden from Swagger)
# =============================================================================


class TestServiceDefaults:
    """Tests for services with default parameters that should be hidden from Swagger"""

    def test_service_with_defaults_hidden_from_swagger(self):
        """Service parameters with defaults should not appear in Swagger"""
        @Injectable
        class ConfigService:
            def __init__(self, precision: int = 5, timeout: int = 30):
                self.precision = precision
                self.timeout = timeout

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/config/{id}")
        def get_config(id: int, service: ConfigService):
            return {
                "id": id,
                "precision": service.precision,
                "timeout": service.timeout
            }

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/config/1")

        assert response.status_code == 200
        assert response.json() == {"id": 1, "precision": 5, "timeout": 30}

        # Check OpenAPI schema - internal params should be hidden
        assert "precision" not in str(app.openapi())
        assert "timeout" not in str(app.openapi())


# =============================================================================
# Test: Router Prefixes and Tags
# =============================================================================


class TestRouterPrefixesAndTags:
    """Tests for InjectableRouter with prefixes and tags"""

    def test_router_with_prefix(self):
        """InjectableRouter works with URL prefix"""
        @Injectable
        class ApiService:
            def get_info(self) -> dict:
                return {"version": "1.0"}

        app = FastAPI()
        router = InjectableRouter(prefix="/api/v1")

        @router.get("/info")
        def info(service: ApiService):
            return service.get_info()

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/api/v1/info")

        assert response.status_code == 200
        assert response.json() == {"version": "1.0"}

    def test_router_with_tags(self):
        """InjectableRouter works with OpenAPI tags"""
        @Injectable
        class UserService:
            pass

        app = FastAPI()
        router = InjectableRouter(prefix="/users", tags=["Users"])

        @router.get("/")
        def list_users(service: UserService):
            return {"users": []}

        @router.get("/{id}")
        def get_user(id: int, service: UserService):
            return {"id": id}

        app.include_router(router)
        client = TestClient(app)

        # Verify routes work
        assert client.get("/users/").status_code == 200
        assert client.get("/users/1").status_code == 200

        # Verify tags in OpenAPI
        openapi = app.openapi()
        assert "/users/" in openapi["paths"]
        assert "Users" in str(openapi)


# =============================================================================
# Test: Multiple Routers in Same App
# =============================================================================


class TestMultipleRouters:
    """Tests for multiple InjectableRouters in the same app"""

    def test_multiple_routers_separate_prefixes(self):
        """Multiple InjectableRouters with different prefixes"""
        @Injectable
        class UserService:
            def get_users(self) -> list:
                return ["user1", "user2"]

        @Injectable
        class ProductService:
            def get_products(self) -> list:
                return ["product1", "product2"]

        app = FastAPI()
        user_router = InjectableRouter(prefix="/users")
        product_router = InjectableRouter(prefix="/products")

        @user_router.get("/")
        def list_users(service: UserService):
            return {"users": service.get_users()}

        @product_router.get("/")
        def list_products(service: ProductService):
            return {"products": service.get_products()}

        app.include_router(user_router)
        app.include_router(product_router)

        client = TestClient(app)

        users_response = client.get("/users/")
        assert users_response.json() == {"users": ["user1", "user2"]}

        products_response = client.get("/products/")
        assert products_response.json() == {"products": ["product1", "product2"]}


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge cases for InjectableRouter"""

    def test_endpoint_without_injectable_params(self):
        """Endpoint without injectable params works normally"""
        app = FastAPI()
        router = InjectableRouter()

        @router.get("/ping")
        def ping(message: str = "pong"):
            return {"message": message}

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"message": "pong"}

    def test_mixed_injectable_and_regular_params(self):
        """Mix of injectable and regular parameters"""
        @Injectable
        class Service:
            def process(self, value: str) -> str:
                return value.upper()

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/process/{id}")
        def process(
            id: int,
            value: str = Query(...),
            service: Service = None,  # Optional to avoid Python arg ordering issues
            limit: int = 10
        ):
            return {
                "id": id,
                "result": service.process(value) if service else value,
                "limit": limit
            }

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/process/1?value=hello")

        assert response.status_code == 200
        assert response.json() == {"id": 1, "result": "HELLO", "limit": 10}

    def test_async_endpoint_with_auto_injection(self):
        """Async endpoints work with auto-injection"""
        @Injectable
        class AsyncService:
            async def fetch_data(self) -> dict:
                return {"data": "async result"}

        app = FastAPI()
        router = InjectableRouter()

        @router.get("/async")
        async def async_endpoint(service: AsyncService):
            result = await service.fetch_data()
            return result

        app.include_router(router)
        client = TestClient(app)
        response = client.get("/async")

        assert response.status_code == 200
        assert response.json() == {"data": "async result"}


# =============================================================================
# Summary  
# =============================================================================


class TestSummary:
    """Summary test to verify InjectableRouter works as expected"""

    def test_injectable_router_complete_example(self):
        """Complete example showing all features work together"""
        @Injectable
        class Repository:
            def get_item(self, id: int) -> dict:
                return {"id": id, "name": f"Item{id}"}

        @Injectable
        class Service:
            def __init__(self, repo: Repository):
                self.repo = repo

            def process_item(self, id: int) -> dict:
                item = self.repo.get_item(id)
                item["processed"] = True
                return item

        app = FastAPI()
        router = InjectableRouter(prefix="/api", tags=["API"])

        @router.get("/items/{id}")
        def get_item(id: int, service: Service):
            """Get and process an item - service auto-injected!"""
            return service.process_item(id)

        @router.post("/items")
        def create_item(item: CreateUserRequest, service: Service):
            """Create an item - service auto-injected!"""
            return {"created": True, "name": item.name}

        app.include_router(router)
        client = TestClient(app)

        # Test GET
        get_response = client.get("/api/items/5")
        assert get_response.status_code == 200
        assert get_response.json() == {
            "id": 5,
            "name": "Item5",
            "processed": True
        }

        # Test POST
        post_response = client.post("/api/items", json={
            "name": "New Item",
            "email": "test@example.com"
        })
        assert post_response.status_code == 200
        assert post_response.json() == {"created": True, "name": "New Item"}

        print("\n✅ InjectableRouter works perfectly! No @AutoInject needed!")
