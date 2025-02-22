#!/usr/bin/env python3

import logging
import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server
import json
import traceback
from typing import Optional, Dict, Any, List
import aiohttp
import os
from datetime import datetime
import ssl
import certifi
from pydantic_settings import BaseSettings

class ClientSettings(BaseSettings):
    # Environment mode
    mode: str = "local"  # "local" or "remote"
    
    # Service URLs - defaults for local development
    librarian_url: str = "http://192.168.1.22:5001"
    codex_url: str = "http://192.168.1.22:5000"
    
    # Remote URLs - used when mode is "remote"
    remote_librarian_url: str = "https://librarian.example.com"
    remote_codex_url: str = "https://codex.example.com"
    
    # API keys for authentication
    librarian_api_key: str = ""
    codex_api_key: str = ""
    
    # Connection settings
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # SSL/TLS settings
    verify_ssl: bool = True
    client_cert: Optional[str] = None
    client_key: Optional[str] = None
    
    class Config:
        env_prefix = "MCP_"
        env_file = ".env"

# Load settings
settings = ClientSettings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mcp_client.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mcp-client")

class ClientError(Exception):
    """Base exception for client errors"""
    pass

class ConnectionError(ClientError):
    """Connection-related errors"""
    pass

class AuthenticationError(ClientError):
    """Authentication-related errors"""
    pass

def format_response(data: Any, error: Optional[str] = None) -> List[TextContent]:
    """Format consistent API response"""
    response = {
        "success": error is None,
        "timestamp": datetime.now().timestamp(),
        "data": data if error is None else None,
        "error": error
    }
    
    return [TextContent(
        type="text",
        text=json.dumps(response, indent=2)
    )]

class MCPClient:
    """Client for interacting with remote Librarian and Codex services"""
    
    def __init__(self):
        # Determine service URLs based on mode
        self.librarian_url = (
            settings.remote_librarian_url if settings.mode == "remote" 
            else settings.librarian_url
        )
        self.codex_url = (
            settings.remote_codex_url if settings.mode == "remote" 
            else settings.codex_url
        )
        
        self.http_session = None
        self.retries = settings.max_retries
        self.retry_delay = settings.retry_delay
        
        # Create SSL context if needed
        self.ssl_context = None
        if settings.mode == "remote":
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
            if settings.client_cert and settings.client_key:
                self.ssl_context.load_cert_chain(
                    settings.client_cert, 
                    settings.client_key
                )

    def _get_headers(self, service: str) -> Dict[str, str]:
        """Get headers for service requests"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Add authentication if configured
        if service == 'librarian' and settings.librarian_api_key:
            headers['X-API-Key'] = settings.librarian_api_key
        elif service == 'codex' and settings.codex_api_key:
            headers['X-API-Key'] = settings.codex_api_key
            
        return headers

    async def setup(self):
        """Initialize the HTTP session"""
        if self.http_session is None:
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=settings.timeout),
                connector=aiohttp.TCPConnector(
                    ssl=self.ssl_context if settings.verify_ssl else False,
                    force_close=True
                )
            )

    async def ensure_session(self):
        """Ensure HTTP session is initialized"""
        if self.http_session is None:
            await self.setup()

    async def close(self):
        """Cleanup resources"""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None

    async def _handle_response(self, response: aiohttp.ClientResponse, service: str) -> Dict:
        """Handle service response and errors"""
        if response.status == 401:
            raise AuthenticationError(f"Authentication failed for {service}")
            
        if response.status == 403:
            raise AuthenticationError(f"Access denied for {service}")
            
        if response.status != 200:
            text = await response.text()
            raise ConnectionError(
                f"{service} request failed with status {response.status}: {text}"
            )
            
        try:
            return await response.json()
        except json.JSONDecodeError as e:
            raise ConnectionError(f"Invalid JSON response from {service}: {e}")

    async def search(self, query: str) -> Dict:
        """Send search query to Librarian"""
        await self.ensure_session()
        headers = self._get_headers('librarian')
        
        for attempt in range(self.retries):
            try:
                async with self.http_session.post(
                    f"{self.librarian_url}/search",
                    headers=headers,
                    json={"query": query}
                ) as response:
                    return await self._handle_response(response, 'librarian')
                    
            except (aiohttp.ClientError, ConnectionError) as e:
                logger.error(f"Search failed (attempt {attempt+1}): {e}")
                if attempt < self.retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise ConnectionError(f"Search failed after {self.retries} attempts: {e}")
            except AuthenticationError:
                raise
            except Exception as e:
                logger.error(f"Unexpected error in search: {e}")
                raise ClientError(f"Search failed: {str(e)}")

    async def call_tool(self, tool_id: str, method: str, arguments: dict) -> Dict:
        """Send tool call to Codex"""
        await self.ensure_session()
        headers = self._get_headers('codex')
        
        for attempt in range(self.retries):
            try:
                async with self.http_session.post(
                    f"{self.codex_url}/call_tool",
                    headers=headers,
                    json={
                        "tool_id": tool_id,
                        "method": method,
                        "arguments": arguments
                    }
                ) as response:
                    return await self._handle_response(response, 'codex')
                    
            except (aiohttp.ClientError, ConnectionError) as e:
                logger.error(f"Tool call failed (attempt {attempt+1}): {e}")
                if attempt < self.retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise ConnectionError(f"Tool call failed after {self.retries} attempts: {e}")
            except AuthenticationError:
                raise
            except Exception as e:
                logger.error(f"Unexpected error in tool call: {e}")
                raise ClientError(f"Tool call failed: {str(e)}")

# Initialize MCP server and client
app = Server("mcp-client")
client = MCPClient()

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="search",
            description="""Query the Librarian service to discover available tools and their capabilities.
            The Librarian analyzes your natural language query and returns detailed information about relevant tools,
            including their purpose, required parameters, and example usage.
            
            Example queries:
            - "I need to analyze my PostgreSQL database"
            - "Tools for processing PDF documents"
            - "How can I interact with Google Calendar?"
            - "I want to automate browser testing"
            - "Looking for tools to manage Trello boards"
            - "Need to analyze GitHub repositories"
            - "Tools for video and image processing"
            - "Help me interact with Slack channels"
            - "I need to work with financial market data"
            
            The Librarian understands hundreds of tool categories including:
            - Database access (MySQL, PostgreSQL, MongoDB, etc.)
            - File operations and document processing
            - API integrations (Trello, Slack, GitHub, etc.)
            - Browser automation and web scraping
            - Calendar and task management
            - Financial data and analysis
            - Image and video processing
            - Cloud services (AWS, GCP, Azure)
            - Development tools and IDE integration
            
            The Librarian will return matching tools with their complete interface definitions,
            making it easy to understand how to use them for your specific needs.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what you're trying to accomplish"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="call_tool",
            description="""Execute a specific tool through the Codex service. Use this after discovering
            appropriate tools via the search function. The Codex will route your request to the correct
            tool service and return the results.
            
            Tool calls require:
            1. tool_id: The unique identifier of the tool (provided by search results)
            2. method: The specific operation to perform
            3. arguments: Parameters required by the method
            
            Example tool calls:
            
            Database query:
            {
                "tool_id": "postgresql_server",
                "method": "execute_query",
                "arguments": {
                    "query": "SELECT * FROM users WHERE active = true",
                    "params": {}
                }
            }
            
            File processing:
            {
                "tool_id": "document_processor",
                "method": "convert_pdf",
                "arguments": {
                    "input_path": "document.pdf",
                    "output_format": "markdown"
                }
            }
            
            Calendar management:
            {
                "tool_id": "google_calendar",
                "method": "create_event",
                "arguments": {
                    "title": "Team Meeting",
                    "start": "2025-02-16T10:00:00Z",
                    "duration_minutes": 60
                }
            }
            
            API integration:
            {
                "tool_id": "trello_manager",
                "method": "create_card",
                "arguments": {
                    "list_id": "123abc",
                    "title": "New Feature",
                    "description": "Implement user authentication"
                }
            }""",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_id": {
                        "type": "string",
                        "description": "Tool identifier returned from search results"
                    },
                    "method": {
                        "type": "string",
                        "description": "Specific method to call on the tool"
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Parameters required by the method (structure defined by tool)"
                    }
                },
                "required": ["tool_id", "method", "arguments"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "search":
            result = await client.search(arguments["query"])
            return format_response(result)
            
        elif name == "call_tool":
            result = await client.call_tool(
                arguments["tool_id"],
                arguments["method"],
                arguments["arguments"]
            )
            return format_response(result)
            
    except AuthenticationError as e:
        logger.error(f"Authentication error in {name}: {e}")
        return format_response(None, f"Authentication failed: {str(e)}")
        
    except ConnectionError as e:
        logger.error(f"Connection error in {name}: {e}")
        return format_response(None, f"Connection failed: {str(e)}")
        
    except ClientError as e:
        logger.error(f"Client error in {name}: {e}")
        return format_response(None, str(e))
        
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}\n{traceback.format_exc()}")
        return format_response(None, f"Internal error: {str(e)}")

async def main():
    logger.info("Starting MCP Client...")
    try:
        # Initialize client session
        await client.setup()
        
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server error: {e}\n{traceback.format_exc()}")
        raise
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())