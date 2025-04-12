#!/usr/bin/env python3

import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
import json
from datetime import datetime, timezone
import uvicorn
import os
import sqlite3
from contextlib import asynccontextmanager
import yaml
import aiohttp
import asyncio
from pathlib import Path
import traceback

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("codex.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("codex-server")

# Constants
DEFAULT_CONFIG_PATH = "config/codex.yaml"
DEFAULT_DB_PATH = "data/codex.db"
REQUIRED_DIRS = ["config", "data", "logs"]

class SearchQuery(BaseModel):
    """Search request model"""
    query: str = Field(..., description="Natural language query to find tools")

class ToolCall(BaseModel):
    """Tool execution request model matching MCP client format"""
    tool_id: str
    method: str  
    arguments: Dict[str, Any]

class ServerConfig(BaseModel):
    """Server configuration model"""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=5000)
    allowed_origins: List[str] = Field(default=["*"])
    db_path: str = Field(default=DEFAULT_DB_PATH)
    tools_config: str = Field(default=DEFAULT_CONFIG_PATH)

class ToolConfig(BaseModel):
    """Tool configuration model"""
    name: str
    description: str
    server: str  # This is the tool file path
    methods: List[str]
    schemas: Dict[str, Dict[str, Any]]

class CodexDB:
    """Database manager for Codex service"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY,
                    results TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id TEXT,
                    method TEXT,
                    arguments TEXT,
                    status TEXT,
                    error TEXT,
                    duration REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_registry (
                    tool_id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    server TEXT,
                    methods TEXT,
                    schemas TEXT,
                    status TEXT,
                    last_check DATETIME
                )
            """)
            
    async def cache_search(self, query: str, results: List[Dict]):
        """Cache search results"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache (query, results) VALUES (?, ?)",
                (query, json.dumps(results))
            )
            
    async def get_cached_search(self, query: str) -> Optional[List[Dict]]:
        """Get cached search results if fresh"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT results, timestamp FROM search_cache 
                   WHERE query = ? AND timestamp > datetime('now', '-1 hour')""",
                (query,)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None
        
    async def log_execution(self, tool_id: str, method: str, arguments: Dict,
                          status: str, error: Optional[str], duration: float):
        """Log tool execution"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO tool_executions 
                   (tool_id, method, arguments, status, error, duration)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tool_id, method, json.dumps(arguments), status, error, duration)
            )
            
    async def register_tool(self, tool: ToolConfig):
        """Register or update tool"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tool_registry
                   (tool_id, name, description, server, methods, schemas, status, last_check)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    tool.name.lower().replace(" ", "_"),
                    tool.name,
                    tool.description,
                    tool.server,
                    json.dumps(tool.methods),
                    json.dumps(tool.schemas),
                    "active"
                )
            )
            
    async def get_tool(self, tool_id: str) -> Optional[Dict]:
        """Get tool configuration"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tool_registry WHERE tool_id = ? AND status = 'active'",
                (tool_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "tool_id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "server": row[3],
                    "methods": json.loads(row[4]),
                    "schemas": json.loads(row[5])
                }
        return None

class ToolExecutor:
    """Handles tool execution through MCP subprocess"""
    
    def __init__(self, db: CodexDB):
        self.db = db
        
    async def execute_tool(self, tool_id: str, method: str, arguments: Dict) -> Dict:
        """Execute tool via MCP subprocess"""
        process = None
        try:
            # Get tool config to find the actual file to execute
            tool = await self.db.get_tool(tool_id)
            if not tool:
                return {
                    "success": False,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "data": None,
                    "error": f"Tool not found: {tool_id}"
                }

            tool_file = tool["server"]  # Use the server field as the tool file path
            
            # Check if file exists
            if not os.path.isfile(tool_file):
                return {
                    "success": False,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "data": None,
                    "error": f"Tool file not found: {tool_file}"
                }
            
            # Make sure file is executable
            try:
                os.chmod(tool_file, os.stat(tool_file).st_mode | 0o111)
            except Exception as e:
                logger.warning(f"Could not set executable permission on {tool_file}: {e}")
            
            # Determine executor based on file extension
            file_extension = tool_file.split('.')[-1].lower()
            executor = None
            if file_extension == 'py':
                executor = 'python'
            elif file_extension in ['js', 'jsx']:
                executor = 'node'
            elif file_extension in ['ts', 'tsx']:
                executor = 'ts-node'
            else:
                return {
                    "success": False,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "data": None,
                    "error": f"Unsupported tool file type: {file_extension}"
                }
                
            logger.info("=== EXECUTING TOOL ===")
            logger.info(f"Tool ID: {tool_id}")
            logger.info(f"Tool File: {tool_file}")
            logger.info(f"Executor: {executor}")
            logger.info(f"Method: {method}")
            logger.info(f"Arguments: {json.dumps(arguments, indent=2)}")

            # Check if the executor is available
            try:
                check_process = await asyncio.create_subprocess_exec(
                    executor, '--version',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await check_process.wait()
                if check_process.returncode != 0:
                    return {
                        "success": False,
                        "timestamp": datetime.now(timezone.utc).timestamp(),
                        "data": None,
                        "error": f"Required executor '{executor}' is not available"
                    }
            except FileNotFoundError:
                return {
                    "success": False,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "data": None,
                    "error": f"Required executor '{executor}' is not installed"
                }

            # Start the tool process
            logger.info(f"Starting tool process with {executor}...")
            
            # Use absolute path for the tool file
            abs_tool_file = os.path.abspath(tool_file)
            logger.info(f"Absolute tool path: {abs_tool_file}")
            
            process = await asyncio.create_subprocess_exec(
                executor, abs_tool_file,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    'PYTHONPATH': os.pathsep.join([os.getcwd(), os.environ.get('PYTHONPATH', '')])
                }
            )

             # Send initialization request
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",  # Use the correct version
                    "clientInfo": {
                        "name": "codex-server",
                        "version": "1.0.0"
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False
                        }
                    }
                }
            }

            # Send init request
            logger.info(f"Sending init request: {json.dumps(init_request)}")
            init_bytes = json.dumps(init_request).encode() + b'\n'
            process.stdin.write(init_bytes)
            await process.stdin.drain()

            # Read initialization response
            init_response_line = await process.stdout.readline()
            if not init_response_line:
                raise RuntimeError("No initialization response received")
            
            init_response = json.loads(init_response_line.decode().strip())
            logger.info(f"Received initialization response: {init_response}")

            if "error" in init_response:
                raise RuntimeError(f"Initialization failed: {init_response['error']}")

            # Send initialized notification with correct format
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {
                    "progressToken": "init",
                    "progress": {
                        "kind": "begin"
                    }
                }
            }
            
            logger.info(f"Sending initialized notification: {json.dumps(initialized_notification)}")
            init_notif_bytes = json.dumps(initialized_notification).encode() + b'\n'
            process.stdin.write(init_notif_bytes)
            await process.stdin.drain()

            # Give the server a moment to process initialization
            await asyncio.sleep(1)

            # Send tool request
            tool_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": method,
                    "arguments": arguments
                }
            }
            
            logger.info(f"Sending tool request: {json.dumps(tool_request)}")
            tool_bytes = json.dumps(tool_request).encode() + b'\n'
            process.stdin.write(tool_bytes)
            await process.stdin.drain()

            # Read tool response with timeout
            try:
                tool_response_line = await asyncio.wait_for(process.stdout.readline(), timeout=30)
                if not tool_response_line:
                    raise RuntimeError("No tool response received")
                    
                tool_response = json.loads(tool_response_line.decode().strip())
                logger.info(f"Received tool response: {tool_response}")
                
                if "error" in tool_response:
                    return {
                        "success": False,
                        "timestamp": datetime.now(timezone.utc).timestamp(),
                        "data": None,
                        "error": f"Tool error: {tool_response['error']}"
                    }

                if "result" in tool_response:
                    return {
                        "success": True,
                        "result": tool_response["result"],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

            except asyncio.TimeoutError:
                raise RuntimeError("Tool response timeout")

            return {
                "success": False,
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "data": None,
                "error": "Invalid response format from tool"
            }

        except Exception as e:
            logger.error(f"Tool execution error: {traceback.format_exc()}")
            return {
                "success": False,
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "data": None,
                "error": f"Tool execution failed: {str(e)}"
            }
        finally:
            if process:
                try:
                    if not process.stdin.is_closing():
                        process.stdin.close()
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                except Exception as e:
                    logger.error(f"Error cleaning up process: {e}")

    async def close(self):
        """Cleanup resources"""
        pass
        
class CodexService:
    """Main Codex service implementation"""
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.db = CodexDB(config.db_path)
        self.executor = ToolExecutor(self.db)
        self.load_tools_config()
        
    async def reload_tools_config(self):
        """Reload tool configurations"""
        try:
            with open(self.config.tools_config) as f:
                config = yaml.safe_load(f)
                
            # Clear existing tools
            async with sqlite3.connect(self.db.db_path) as conn:
                await conn.execute("DELETE FROM tool_registry")
                
            # Register new tools
            for tool_config in config.get("tools", []):
                await self.db.register_tool(ToolConfig(**tool_config))
                
            logger.info("Tool configurations reloaded successfully")
            
        except Exception as e:
            logger.error(f"Error reloading tools config: {str(e)}")
            raise
            
    def load_tools_config(self):
        """Initial load of tool configurations"""
        try:
            with open(self.config.tools_config) as f:
                config = yaml.safe_load(f)
                
            for tool_config in config.get("tools", []):
                asyncio.create_task(
                    self.db.register_tool(ToolConfig(**tool_config))
                )
                
        except Exception as e:
            logger.error(f"Error loading tools config: {str(e)}")
            raise
            
    async def search_tools(self, query: str) -> List[Dict]:
        """Search for tools matching query"""
        # Check cache first
        cached = await self.db.get_cached_search(query)
        if cached:
            return cached
            
        # Simple search implementation for now
        query = query.lower()
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tool_registry WHERE status = 'active'"
            )
            matches = []
            for row in cursor:
                tool = {
                    "tool_id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "methods": json.loads(row[4]),
                    "schemas": json.loads(row[5])
                }
                if (query in tool["name"].lower() or 
                    query in tool["description"].lower()):
                    matches.append(tool)
                    
        # Cache results
        await self.db.cache_search(query, matches)
        return matches
        
    async def execute_tool(self, tool_id: str, method: str, arguments: Dict) -> Dict:
        """Execute a tool"""
        start_time = datetime.now(timezone.utc)
        status = "success"
        error = None
        
        try:
            # Get tool config
            tool = await self.db.get_tool(tool_id)
            if not tool:
                return {
                    "success": False,
                    "error": f"Tool {tool_id} not found. The tool may need to be installed.",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            if method not in tool["methods"]:
                return {
                    "success": False,
                    "error": f"Method {method} not supported by tool {tool_id}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            # Execute tool
            try:
                result = await self.executor.execute_tool(
                    tool_id,
                    method,
                    arguments
                )
                
                return {
                    "success": True,
                    "result": result,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            except Exception as e:
                error = str(e)
                logger.error(f"Error executing tool: {traceback.format_exc()}")
                return {
                    "success": False,
                    "error": f"Tool execution failed: {error}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            error = str(e)
            logger.error(f"Unexpected error: {traceback.format_exc()}")
            return {
                "success": False,
                "error": f"Internal error: {error}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            await self.db.log_execution(
                tool_id, method, arguments, status, error, duration
            )
            
    async def cleanup(self):
        """Cleanup resources"""
        await self.executor.close()

def create_dirs():
    """Create required directories"""
    for dir_name in REQUIRED_DIRS:
        os.makedirs(dir_name, exist_ok=True)

# Create FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_dirs()
    config = ServerConfig()  # Load from env/file if needed
    service = CodexService(config)
    app.state.service = service
    
    yield
    
    # Cleanup
    await service.cleanup()

app = FastAPI(
    title="Codex Service",
    description="Tool discovery and execution service",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled error: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": f"Internal server error: {str(exc)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/reload")
async def reload_config(request: Request):
    """Reload tool configurations"""
    try:
        await request.app.state.service.reload_tools_config()
        return {
            "success": True,
            "message": "Tool configurations reloaded",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Config reload failed: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload configurations: {str(e)}"
        )

@app.post("/search")
async def search(query: SearchQuery, request: Request):
    """Search for tools matching query"""
    try:
        matches = await request.app.state.service.search_tools(query.query)
        return {
            "success": True,
            "tools": matches,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Search error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )

@app.post("/call_tool")
async def call_tool(request: ToolCall, req: Request):
    """Execute tool method"""
    try:
        # Log incoming request
        logger.info("=== CALL_TOOL REQUEST ===")
        logger.info(f"Tool ID: {request.tool_id}")
        logger.info(f"Method: {request.method}")
        logger.info(f"Arguments: {json.dumps(request.arguments, indent=2)}")
        logger.info("========================")

        result = await req.app.state.service.execute_tool(
            request.tool_id,
            request.method,
            request.arguments
        )
        
        # Log result
        logger.info("=== CALL_TOOL RESPONSE ===")
        logger.info(json.dumps(result, indent=2))
        logger.info("==========================")
        
        return {
            "success": True,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool execution error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Tool execution failed: {str(e)}"
        )

def main():
    """Run the Codex service"""
    # Load config from env/file if needed
    config = ServerConfig()
    
    logger.info(f"Starting Codex service on {config.host}:{config.port}")
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info"
    )

if __name__ == "__main__":
    main()