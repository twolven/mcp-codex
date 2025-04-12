#!/usr/bin/env python3

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("test-server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test-server")

# Create FastAPI app
app = FastAPI(title="Test Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(path: str, request: Request):
    """Catch and log all requests"""
    logger.info("=== INCOMING REQUEST ===")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Path: {path}")
    logger.info(f"Method: {request.method}")
    
    # Log headers
    logger.info("Headers:")
    for name, value in request.headers.items():
        logger.info(f"  {name}: {value}")
    
    # Log query params
    logger.info("Query Params:")
    for name, value in request.query_params.items():
        logger.info(f"  {name}: {value}")
    
    # Log body if present
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
            logger.info("Body:")
            logger.info(json.dumps(body, indent=2))
        except:
            body = await request.body()
            logger.info(f"Raw Body: {body}")
    
    logger.info("=====================")
    
    # Return request details
    response = {
        "message": "Request received and logged",
        "timestamp": datetime.now().isoformat(),
        "details": {
            "path": path,
            "method": request.method,
            "headers": dict(request.headers),
            "query_params": dict(request.query_params)
        }
    }
    
    if request.method in ["POST", "PUT"]:
        try:
            response["details"]["body"] = await request.json()
        except:
            response["details"]["body"] = str(await request.body())
    
    return response

def main():
    """Run the test server"""
    host = "0.0.0.0"
    port = 5000
    
    logger.info(f"Starting test server on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    main()