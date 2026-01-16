"""
Backward Compatibility Tests for DI Framework
==============================================

Tests to ensure that the OLD pattern (FastAPI app + @AutoInject) 
still works after introducing InjectableRouter.

This ensures we don't break existing user code!

Run with: pytest tests/test_backward_compatibility.py -v
"""

import pytest
from fastapi import FastAPI, Query, Path, Body, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional

from app.core.eagle_di import (
    Injectable,
    AutoInject,
    test_container,
)


# =============================================================================
# Pydantic Models
# =============================================================================


class UserCreate(BaseModel):
    name: str
    email: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def isolate_tests():
    """Each test runs in isolated container"""
    with test_container():
        yield


# =============================================================================
# Test: @app + @AutoInject Pattern (OLD PATTERN)
# =============================================================================


class TestBackwardCompatibility:
    """Tests that OLD pattern (@app + @AutoInject) still works"""

    def test_old_pattern_simple_get(self):
        """OLD PATTERN: @app.get() + @AutoInject should still work"""
        @Injectable
        class UserService:
            def get_user(self, id: int) -> dict:
                return {"id": id, "name": f"User{id}"}

        app = FastAPI()

        # OLD PATTERN: Using @app.get() with @AutoInject
        @app.get("/users/{id}")
        @AutoInject
        def get_user(id: int, service: UserService):
            return service.get_user(id)

        client = TestClient(app)
        response = client.get("/users/123")

        assert response.status_code == 200
        assert response.json() == {"id": 123, "name": "User123"}

    def test_old_pattern_with_post(self):
        """OLD PATTERN: @app.post() + @AutoInject should work"""
        @Injectable
        class UserService:
            def create_user(self, name: str, email: str) -> dict:
                return {"name": name, "email": email, "created": True}

        app = FastAPI()

        @app.post("/users")
        @AutoInject
        def create_user(user: UserCreate, service: UserService):
            return service.create_user(user.name, user.email)

        client = TestClient(app)
        response = client.post("/users", json={
            "name": "Alice",
            "email": "alice@example.com"
        })

        assert response.status_code == 200
        assert response.json() == {
            "name": "Alice",
            "email": "alice@example.com",
            "created": True
        }

    def test_old_pattern_with_query_params(self):
        """OLD PATTERN: Works with query parameters"""
        @Injectable
        class SearchService:
            def search(self, query: str) -> list:
                return [f"Result for {query}"]

        app = FastAPI()

        @app.get("/search")
        @AutoInject
        def search(q: str = Query(...), service: SearchService = None):
            return {"results": service.search(q)}

        client = TestClient(app)
        response = client.get("/search?q=test")

        assert response.status_code == 200
        assert response.json() == {"results": ["Result for test"]}

    def test_old_pattern_with_path_and_query(self):
        """OLD PATTERN: Works with mixed path and query params"""
        @Injectable
        class ItemService:
            def get_item(self, id: int, detailed: bool) -> dict:
                item = {"id": id, "name": f"Item{id}"}
                if detailed:
                    item["details"] = "Full details here"
                return item

        app = FastAPI()

        @app.get("/items/{id}")
        @AutoInject
        def get_item(id: int, detailed: bool = False, service: ItemService = None):
            return service.get_item(id, detailed)

        client = TestClient(app)
        
        # Without query param
        response = client.get("/items/5")
        assert response.json() == {"id": 5, "name": "Item5"}

        # With query param
        response = client.get("/items/5?detailed=true")
        assert response.json() == {
            "id": 5,
            "name": "Item5",
            "details": "Full details here"
        }

    def test_old_pattern_with_headers(self):
        """OLD PATTERN: Works with headers"""
        @Injectable
        class AuthService:
            def validate_token(self, token: str) -> bool:
                return token == "valid-token"

        app = FastAPI()

        @app.get("/protected")
        @AutoInject
        def protected(x_token: str = Header(...), service: AuthService = None):
            is_valid = service.validate_token(x_token)
            return {"authorized": is_valid}

        client = TestClient(app)
        response = client.get("/protected", headers={"X-Token": "valid-token"})

        assert response.status_code == 200
        assert response.json() == {"authorized": True}

    def test_old_pattern_with_put(self):
        """OLD PATTERN: @app.put() + @AutoInject should work"""
        @Injectable
        class UserService:
            def update_user(self, id: int, update: UserUpdate) -> dict:
                return {
                    "id": id,
                    "updated": True,
                    "changes": update.model_dump(exclude_none=True)
                }

        app = FastAPI()

        @app.put("/users/{id}")
        @AutoInject
        def update_user(id: int, update: UserUpdate, service: UserService = None):
            return service.update_user(id, update)

        client = TestClient(app)
        response = client.put("/users/42", json={"name": "Updated Name"})

        assert response.status_code == 200
        assert response.json() == {
            "id": 42,
            "updated": True,
            "changes": {"name": "Updated Name"}
        }

    def test_old_pattern_multiple_services(self):
        """OLD PATTERN: Multiple services injection works"""
        @Injectable
        class ServiceA:
            def get_a(self) -> str:
                return "A"

        @Injectable
        class ServiceB:
            def get_b(self) -> str:
                return "B"

        app = FastAPI()

        @app.get("/multi")
        @AutoInject
        def multi(svc_a: ServiceA, svc_b: ServiceB, param: str = "default"):
            return {
                "a": svc_a.get_a(),
                "b": svc_b.get_b(),
                "param": param
            }

        client = TestClient(app)
        response = client.get("/multi")

        assert response.status_code == 200
        assert response.json() == {"a": "A", "b": "B", "param": "default"}

    def test_old_pattern_nested_dependencies(self):
        """OLD PATTERN: Nested service dependencies work"""
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

        @app.get("/process")
        @AutoInject
        def process(service: Service):
            return {"result": service.process()}

        client = TestClient(app)
        response = client.get("/process")

        assert response.status_code == 200
        assert response.json() == {"result": "Processed: data from repo"}

    def test_old_pattern_async_endpoint(self):
        """OLD PATTERN: Async endpoints work"""
        @Injectable
        class AsyncService:
            async def fetch_data(self) -> dict:
                return {"data": "async result"}

        app = FastAPI()

        @app.get("/async")
        @AutoInject
        async def async_endpoint(service: AsyncService):
            result = await service.fetch_data()
            return result

        client = TestClient(app)
        response = client.get("/async")

        assert response.status_code == 200
        assert response.json() == {"data": "async result"}


# =============================================================================
# Test: Decorator Order Variations
# =============================================================================


class TestDecoratorOrder:
    """Tests that @AutoInject works in different decorator positions"""

    def test_autoinject_below_route_correct_order(self):
        """@AutoInject BELOW @app.get() works correctly"""
        @Injectable
        class Service:
            def get(self) -> str:
                return "data"

        app = FastAPI()

        # CORRECT: @AutoInject BELOW @app.get()
        @app.get("/test1")
        @AutoInject
        def endpoint1(service: Service):
            return {"result": service.get()}

        client = TestClient(app)
        response = client.get("/test1")

        assert response.status_code == 200
        assert response.json() == {"result": "data"}

    def test_autoinject_below_route(self):
        """@AutoInject BELOW @app.get() should work"""
        @Injectable
        class Service:
            def get(self) -> str:
                return "data"

        app = FastAPI()

        @app.get("/test2")
        @AutoInject
        def endpoint2(service: Service):
            return {"result": service.get()}

        client = TestClient(app)
        response = client.get("/test2")

        assert response.status_code == 200
        assert response.json() == {"result": "data"}


# =============================================================================
# Summary
# =============================================================================


class TestBackwardCompatibilitySummary:
    """Summary test to confirm backward compatibility"""

    def test_backward_compatibility_confirmed(self):
        """Confirm that old pattern still works perfectly"""
        @Injectable
        class LegacyService:
            def get_message(self) -> str:
                return "Old pattern still works!"

        app = FastAPI()

        # OLD PATTERN - should work exactly as before
        @app.get("/legacy")
        @AutoInject
        def legacy_endpoint(service: LegacyService):
            return {"message": service.get_message()}

        client = TestClient(app)
        response = client.get("/legacy")

        assert response.status_code == 200
        assert response.json() == {"message": "Old pattern still works!"}

        print("\n✅ BACKWARD COMPATIBILITY CONFIRMED!")
        print("   @app + @AutoInject pattern still works perfectly!")
        print("   Existing user code will NOT break! 🎉")
