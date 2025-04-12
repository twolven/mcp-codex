#!/usr/bin/env python3

import logging
import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server
import json
import traceback
from datetime import datetime
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG level
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("test-tool.log"),
        logging.StreamHandler(sys.stderr)  # Explicitly log to stderr
    ]
)
logger = logging.getLogger("test-tool")

app = Server("test-tool")

@app.list_tools()
async def list_tools():
    logger.debug("list_tools called")
    return [
        Tool(
            name="get_test_data",
            description="Test method that returns sample data",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string",
                        "description": "ID for test data"
                    },
                    "include_details": {
                        "type": "boolean",
                        "description": "Include additional details"
                    }
                },
                "required": ["test_id"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    logger.debug(f"call_tool called with name: {name}, arguments: {arguments}")
    
    if name == "get_test_data":
        response = {
            "test_id": arguments.get("test_id"),
            "timestamp": datetime.now().isoformat(),
            "data": {
                "message": "Test successful",
                "details": {
                    "additional": "information"
                } if arguments.get("include_details") else None
            }
        }
        
        # Convert response to TextContent
        result = TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "data": response,
                "error": None
            })
        )
        logger.debug(f"Returning response: {result}")
        return [result]
    
    result = TextContent(
        type="text",
        text=json.dumps({
            "success": False,
            "data": None,
            "error": f"Unknown method: {name}"
        })
    )
    logger.debug(f"Returning error: {result}")
    return [result]

async def main():
    logger.info("Starting test tool...")
    try:
        logger.debug("Creating stdio server")
        async with stdio_server() as (read_stream, write_stream):
            logger.debug("Got stdio streams, creating initialization options")
            init_options = app.create_initialization_options()
            logger.debug(f"Initialization options: {init_options}")
            logger.debug("Running app")
            await app.run(
                read_stream,
                write_stream,
                init_options
            )
    except Exception as e:
        logger.error(f"Server error: {e}\n{traceback.format_exc()}")
        raise
    finally:
        logger.info("Test tool shutting down")

if __name__ == "__main__":
    logger.info("Test tool script started")
    asyncio.run(main())