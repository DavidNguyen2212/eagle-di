"""
FastAPI Integration Tests for DI Utility
==========================================

Tests to verify that DI works seamlessly with FastAPI:
- Path parameters
- Query parameters
- Request body (Pydantic models)
- Headers
- Combined parameters

Run with: pytest tests/unit/DI/test_fastapi_integration.py -v
"""

from fastapi import FastAPI, Query, Path, Body, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional, Annotated

from app.core.eagle_di import (
    Injectable,
    AutoInject,
    test_container,
)


# =============================================================================
# Pydantic Models (these are fine at module level)
# =============================================================================


class UserCreate(BaseModel):
    name: str
    email: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class OrderCreate(BaseModel):
    product_id: int
    quantity: int
    notes: Optional[str] = None


# =============================================================================
# Level 1: Basic - Path Parameters Only
# =============================================================================


class TestLevel1PathParams:
    """DI + Path parameters"""

    def test_single_path_param(self):
        """DI with single path parameter"""
        with test_container():
            @Injectable
            class UserService:
                def get_user(self, user_id: int) -> dict:
                    return {"id": user_id, "name": f"User{user_id}"}

            app = FastAPI()

            @app.get("/users/{user_id}")
            @AutoInject
            def get_user(user_id: int, service: UserService):
                return service.get_user(user_id)

            client = TestClient(app)
            response = client.get("/users/123")
            
            assert response.status_code == 200
            assert response.json() == {"id": 123, "name": "User123"}

    def test_multiple_path_params(self):
        """DI with multiple path parameters"""
        with test_container():
            @Injectable
            class UserService:
                def get_user(self, user_id: int) -> dict:
                    return {"id": user_id, "name": f"User{user_id}"}

            app = FastAPI()

            @app.get("/orgs/{org_id}/users/{user_id}")
            @AutoInject
            def get_org_user(org_id: int, user_id: int, service: UserService):
                user = service.get_user(user_id)
                user["org_id"] = org_id
                return user

            client = TestClient(app)
            response = client.get("/orgs/10/users/5")
            
            assert response.status_code == 200
            assert response.json() == {"id": 5, "name": "User5", "org_id": 10}


# =============================================================================
# Level 2: Query Parameters
# =============================================================================


class TestLevel2QueryParams:
    """DI + Query parameters"""

    def test_required_query_param(self):
        """DI with required query parameter"""
        with test_container():
            @Injectable
            class SimpleService:
                def greet(self, name: str) -> str:
                    return f"Hello, {name}!"

            app = FastAPI()

            @app.get("/search")
            @AutoInject
            def search(q: str, service: SimpleService):
                return {"query": q, "greeting": service.greet(q)}

            client = TestClient(app)
            response = client.get("/search?q=World")
            
            assert response.status_code == 200
            assert response.json() == {"query": "World", "greeting": "Hello, World!"}

    def test_optional_query_param(self):
        """DI with optional query parameter"""
        with test_container():
            @Injectable
            class SimpleService:
                def greet(self, name: str) -> str:
                    return f"Hello, {name}!"

            app = FastAPI()

            @app.get("/greet")
            @AutoInject
            def greet(name: str = "Guest", service: SimpleService = None):
                return {"greeting": service.greet(name)}

            client = TestClient(app)
            
            # Without query param
            response = client.get("/greet")
            assert response.json() == {"greeting": "Hello, Guest!"}
            
            # With query param
            response = client.get("/greet?name=Alice")
            assert response.json() == {"greeting": "Hello, Alice!"}

    def test_query_with_validation(self):
        """DI with Query() validation"""
        with test_container():
            @Injectable
            class SimpleService:
                pass

            app = FastAPI()

            @app.get("/items")
            @AutoInject
            def get_items(
                skip: int = Query(0, ge=0),
                limit: int = Query(10, le=100),
                service: SimpleService = None
            ):
                return {"skip": skip, "limit": limit}

            client = TestClient(app)
            response = client.get("/items?skip=5&limit=20")
            
            assert response.status_code == 200
            assert response.json() == {"skip": 5, "limit": 20}


# =============================================================================
# Level 3: Request Body (Pydantic Models)
# =============================================================================


class TestLevel3RequestBody:
    """DI + Pydantic request body"""

    def test_simple_body(self):
        """DI with simple Pydantic body"""
        with test_container():
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

    def test_body_with_optional_fields(self):
        """DI with Pydantic body containing optional fields"""
        with test_container():
            @Injectable
            class UserService:
                pass

            app = FastAPI()

            @app.post("/orders")
            @AutoInject
            def create_order(order: OrderCreate, service: UserService):
                return {
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                    "notes": order.notes
                }

            client = TestClient(app)
            
            # Without optional field
            response = client.post("/orders", json={
                "product_id": 1,
                "quantity": 5
            })
            assert response.json()["notes"] is None
            
            # With optional field
            response = client.post("/orders", json={
                "product_id": 1,
                "quantity": 5,
                "notes": "Rush order"
            })
            assert response.json()["notes"] == "Rush order"


# =============================================================================
# Level 4: Headers
# =============================================================================


class TestLevel4Headers:
    """DI + Header parameters"""

    def test_required_header(self):
        """DI with required header"""
        with test_container():
            @Injectable
            class SimpleService:
                pass

            app = FastAPI()

            @app.get("/protected")
            @AutoInject
            def protected(x_token: str = Header(), service: SimpleService = None):
                return {"token": x_token}

            client = TestClient(app)
            response = client.get("/protected", headers={"X-Token": "secret123"})
            
            assert response.status_code == 200
            assert response.json() == {"token": "secret123"}

    def test_optional_header(self):
        """DI with optional header"""
        with test_container():
            @Injectable
            class SimpleService:
                pass

            app = FastAPI()

            @app.get("/info")
            @AutoInject
            def info(
                x_request_id: Optional[str] = Header(None),
                service: SimpleService = None
            ):
                return {"request_id": x_request_id}

            client = TestClient(app)
            
            # Without header
            response = client.get("/info")
            assert response.json() == {"request_id": None}
            
            # With header
            response = client.get("/info", headers={"X-Request-ID": "req-123"})
            assert response.json() == {"request_id": "req-123"}


# =============================================================================
# Level 5: Combined (All Together)
# =============================================================================


class TestLevel5Combined:
    """DI + Multiple FastAPI features combined"""

    def test_path_query_body_header(self):
        """DI with path, query, body, and header all together"""
        with test_container():
            @Injectable
            class UserService:
                pass

            app = FastAPI()

            @app.put("/users/{user_id}")
            @AutoInject
            def update_user(
                user_id: int,
                update: UserUpdate,
                dry_run: bool = Query(False),
                x_admin_key: str = Header(),
                service: UserService = None
            ):
                result = {
                    "user_id": user_id,
                    "update": update.model_dump(exclude_none=True),
                    "dry_run": dry_run,
                    "admin": x_admin_key == "admin123"
                }
                return result

            client = TestClient(app)
            response = client.put(
                "/users/42?dry_run=true",
                json={"name": "Updated Name"},
                headers={"X-Admin-Key": "admin123"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == 42
            assert data["update"] == {"name": "Updated Name"}
            assert data["dry_run"] is True
            assert data["admin"] is True

    def test_nested_services_with_all_params(self):
        """DI with nested services and all param types"""
        with test_container():
            @Injectable
            class UserService:
                def get_user(self, user_id: int) -> dict:
                    return {"id": user_id, "name": f"User{user_id}"}

            @Injectable
            class CompositeService:
                def __init__(self, user_service: UserService):
                    self.user_service = user_service
                
                def get_user_greeting(self, user_id: int) -> str:
                    user = self.user_service.get_user(user_id)
                    return f"Welcome, {user['name']}!"

            app = FastAPI()

            @app.post("/orgs/{org_id}/users/{user_id}/greet")
            @AutoInject
            def greet_user(
                org_id: int,
                user_id: int,
                message: Optional[str] = Query(None),
                x_lang: str = Header("en"),
                service: CompositeService = None
            ):
                base_greeting = service.get_user_greeting(user_id)
                return {
                    "org_id": org_id,
                    "greeting": base_greeting,
                    "custom_message": message,
                    "language": x_lang
                }

            client = TestClient(app)
            response = client.post(
                "/orgs/1/users/100/greet?message=Welcome!",
                headers={"X-Lang": "de"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["org_id"] == 1
            assert data["greeting"] == "Welcome, User100!"
            assert data["custom_message"] == "Welcome!"
            assert data["language"] == "de"


# =============================================================================
# Level 6: Edge Cases
# =============================================================================


class TestLevel6EdgeCases:
    """Edge cases and potential conflicts"""

    def test_service_parameter_order_first(self):
        """
        Service as first parameter - LIMITATION
        Python requires default args before non-default args.
        So service (which becomes Depends) must have = None when before required params.
        """
        with test_container():
            @Injectable
            class SimpleService:
                pass

            app = FastAPI()

            # NOTE: Service MUST have default (= None) when placed before required params
            @app.get("/test1/{id}")
            @AutoInject
            def test1(service: SimpleService = None, id: int = Path()):
                return {"id": id}

            client = TestClient(app)
            response = client.get("/test1/5")
            assert response.json() == {"id": 5}

    def test_service_parameter_order_middle(self):
        """Service in middle of parameters"""
        with test_container():
            @Injectable
            class SimpleService:
                pass

            app = FastAPI()

            @app.get("/test2/{id}")
            @AutoInject
            def test2(id: int, service: SimpleService, name: str = "default"):
                return {"id": id, "name": name}

            client = TestClient(app)
            response = client.get("/test2/5?name=test")
            assert response.json() == {"id": 5, "name": "test"}

    def test_multiple_services(self):
        """Multiple services injected"""
        with test_container():
            @Injectable
            class SimpleService:
                def greet(self, name: str) -> str:
                    return f"Hello, {name}!"

            @Injectable
            class UserService:
                def get_user(self, user_id: int) -> dict:
                    return {"id": user_id, "name": f"User{user_id}"}

            app = FastAPI()

            @app.get("/multi")
            @AutoInject
            def multi(
                svc1: SimpleService,
                svc2: UserService,
                name: str = "World"
            ):
                return {
                    "greeting": svc1.greet(name),
                    "user": svc2.get_user(1)
                }

            client = TestClient(app)
            response = client.get("/multi")
            
            assert response.status_code == 200
            data = response.json()
            assert data["greeting"] == "Hello, World!"
            assert data["user"]["id"] == 1


# =============================================================================
# Summary Test
# =============================================================================


class TestSummary:
    """Summary test to show everything works"""

    def test_all_features_work(self):
        """Prove DI doesn't break any FastAPI features"""
        with test_container():
            @Injectable
            class SimpleService:
                pass

            app = FastAPI()
            
            # 1. Path params
            @app.get("/t1/{id}")
            @AutoInject
            def t1(id: int, s: SimpleService): 
                return {"ok": True}
            
            # 2. Query params
            @app.get("/t2")
            @AutoInject  
            def t2(q: str = "x", s: SimpleService = None): 
                return {"ok": True}
            
            # 3. Body
            @app.post("/t3")
            @AutoInject
            def t3(b: UserCreate, s: SimpleService = None): 
                return {"ok": True}
            
            # 4. Headers
            @app.get("/t4")
            @AutoInject
            def t4(h: str = Header("x"), s: SimpleService = None): 
                return {"ok": True}

            client = TestClient(app)
            
            assert client.get("/t1/1").status_code == 200
            assert client.get("/t2").status_code == 200
            assert client.post("/t3", json={"name": "a", "email": "b"}).status_code == 200
            assert client.get("/t4").status_code == 200
            
            print(f"\n✅ All FastAPI features work with DI!")
