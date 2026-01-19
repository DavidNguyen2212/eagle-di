"""
AWS Lambda Entry Point Example
==============================

This file shows how to integrate Eagle DI with AWS Lambda.
Copy this to your project's app/main.py (or create a separate handler.py).

Requirements:
    pip install mangum

Deployment:
    1. SAM: sam deploy --guided
    2. Serverless: serverless deploy --stage dev
"""

from fastapi import FastAPI

from app.core.eagle_di import (
    Injectable,
    InjectableRouter,
    get_service,
    process_async_inits,
)
from app.core.serverless import (
    LambdaAdapter,
    OnColdStart,
    OnWarmUp,
    ServerlessDatabaseProvider,
    Timeout,
)

# =============================================================================
# DATABASE SETUP (Optional)
# =============================================================================

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Only create if DATABASE_URL is set
db = None
if DATABASE_URL:
    db = ServerlessDatabaseProvider(DATABASE_URL)


# =============================================================================
# SERVICES
# =============================================================================


@Injectable
class HealthService:
    """Simple health check service."""
    
    def check(self) -> dict:
        return {"status": "healthy", "platform": "aws-lambda"}


@Injectable
class UserService:
    """Example user service."""
    
    async def get_user(self, user_id: int) -> dict:
        # In real app, query database
        return {"id": user_id, "name": f"User {user_id}"}
    
    async def list_users(self, limit: int = 10) -> list:
        return [{"id": i, "name": f"User {i}"} for i in range(1, limit + 1)]


# =============================================================================
# LIFECYCLE HOOKS
# =============================================================================


@OnColdStart
async def init_services():
    """Initialize services on cold start."""
    print("🚀 Cold start: Initializing services...")
    
    # Process DI async inits
    await process_async_inits()
    
    # Warm up database if configured
    if db:
        await db.warmup()
    
    print("✅ Cold start complete")


@OnWarmUp
async def warmup_cache():
    """Warmup for provisioned concurrency."""
    print("🔥 Warming up cache...")
    # Pre-load frequently accessed data
    pass


# =============================================================================
# ROUTES
# =============================================================================

router = InjectableRouter(prefix="/api/v1", tags=["API"])


@router.get("/health")
async def health_check(service: HealthService):
    """Health check endpoint."""
    return service.check()


@router.get("/users/{user_id}")
@Timeout(25)  # Leave 5s buffer for Lambda's 30s limit
async def get_user(user_id: int, service: UserService):
    """Get user by ID."""
    return await service.get_user(user_id)


@router.get("/users")
async def list_users(limit: int = 10, service: UserService = None):
    """List users."""
    return await service.list_users(limit)


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="Eagle DI on AWS Lambda",
    description="FastAPI + Eagle DI deployed to AWS Lambda",
    version="1.0.0",
)

app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Eagle DI on AWS Lambda",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# =============================================================================
# LAMBDA HANDLER
# =============================================================================

# Create Lambda adapter
adapter = LambdaAdapter(
    app,
    lifespan="auto",
    api_gateway_base_path="/",
)

# Export handler for Lambda
handler = adapter.handler


# =============================================================================
# LOCAL DEVELOPMENT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("Running in local development mode...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
