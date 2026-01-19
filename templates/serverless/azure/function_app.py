"""
Azure Functions Entry Point for Eagle DI FastAPI Application

This file demonstrates how to integrate Eagle DI with Azure Functions.
Copy this to your function_app.py and customize as needed.

Requirements:
    pip install azure-functions

Usage:
    1. Copy this file to your Azure Functions project
    2. Update the import paths for your app
    3. Deploy with: func azure functionapp publish <app-name>
"""

import azure.functions as func
from app.core.serverless import AzureFunctionsAdapter, OnColdStart

# Import your FastAPI app
# from app.main import app
from fastapi import FastAPI

# Create FastAPI app (or import existing)
app = FastAPI(title="Eagle DI on Azure Functions")


@app.get("/")
async def root():
    return {"message": "Hello from Azure Functions!", "framework": "Eagle DI"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Create Azure Functions adapter
adapter = AzureFunctionsAdapter(app)


# Cold start initialization
@OnColdStart
async def init_services():
    """Initialize services on cold start."""
    # await db.connect()
    # await cache.connect()
    pass


# Create Function App
function_app = func.FunctionApp()


@function_app.route(route="{*route}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """Main HTTP trigger that routes all requests to FastAPI."""
    return await adapter.handle(req)


# Health check endpoint (for Azure Load Balancer)
@function_app.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Dedicated health check for Azure."""
    return func.HttpResponse(
        body='{"status": "healthy"}',
        status_code=200,
        mimetype="application/json"
    )
