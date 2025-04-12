# MCP-Codex: Model Context Protocol Tool Orchestration

DISCLAIMER: This project was discontinued after Cloudflare released a similar service that addressed many of the same problems. I'm sharing this codebase as an educational resource and example of MCP orchestration architecture. While no longer actively developed, the concepts and implementations may still be valuable to those interested in AI tool orchestration.  Please see Cloudflare's new Remote MCP service and their blogpost announcement here:  https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/

![License](https://img.shields.io/badge/license-MIT-blue.svg)

A service for orchestrating Model Context Protocol (MCP) servers and allowing AI assistants to dynamically discover and utilize tools without requiring restarts, powered by "The Librarian" - an intelligent agent that understands user needs and connects them with the perfect tools.

## Overview

MCP-Codex solves a core problem with the Model Context Protocol ecosystem: the need to restart AI assistants when adding new tools. It enables dynamic tool discovery and execution through a central service, allowing AI assistants to use any compatible MCP tool on demand.

### The Librarian: Intelligent Tool Discovery

At the heart of MCP-Codex is "The Librarian" - an intelligent agent designed to understand user needs and connect them with the right tools. The Librarian functions as an agentic RAG (Retrieval-Augmented Generation) system with:

- **Multi-Vector Knowledge Base**: Separate vector databases for industry knowledge and internal documentation
- **MCP Repository Awareness**: Deep understanding of available MCP tools across the ecosystem
- **Just-in-Time Tool Installation**: Capability to install tools on-demand before they're needed
- **Context-Aware Recommendations**: Uses the full context of user queries to identify the optimal tools
- **Seamless Integration**: Handles all details of tool discovery, installation, and execution

The Librarian effectively serves as a universal adapter between user intent and technical capabilities, eliminating the cognitive load of tool selection for both users and AI assistants.

### The Problem

Model Context Protocol (MCP) is a powerful standard for connecting AI assistants to external tools and data sources. However, traditional MCP implementations have a significant limitation:

- **Static Configuration**: Tools must be configured at startup, requiring restarts whenever new capabilities are needed
- **Local-Only Operation**: Tools typically run on the same machine as the assistant
- **Limited Discovery**: Assistants have no standardized way to discover what tools are available
- **High Cognitive Load**: Users must know exactly which tool they need for a specific task

### The Solution

MCP-Codex provides a bridge between AI assistants and the broader MCP ecosystem by offering:

1. **Intelligent Tool Discovery**: The Librarian service analyzes user intent and recommends the perfect tools
2. **Dynamic Tool Management**: Tools can be installed, configured, and executed on-demand
3. **Remote Execution**: Tools can run anywhere, not just on the local machine
4. **Centralized Management**: Tools can be added, updated, or removed without restarting assistants
5. **Standardized Protocol**: A consistent interface for interacting with any MCP tool

## Architecture

The project consists of three main components:

1. **Codex Service** (`codex-serv.py`): The core execution service that manages tool discovery and invocation
2. **Librarian Service** (planned): An AI-powered tool recommendation system
3. **MCP Client** (`mcp-codex.py`): The MCP-compatible interface for AI assistants

### How It Works

1. The AI assistant connects to the MCP-Codex client
2. The client presents two main tools: `search` and `call_tool`
3. The assistant can search for capabilities using natural language
4. Once a tool is identified, it can be executed through a standardized call
5. The Codex service handles the actual tool execution and returns results

## Components

### Codex Service

The central orchestration service that:
- Manages the registry of available MCP tools
- Handles tool execution requests
- Routes requests to the appropriate tool subprocess
- Manages tool lifecycle

### MCP Client

The MCP-compliant interface that allows any MCP-compatible assistant to:
- Connect to the Codex ecosystem
- Search for available tools
- Execute tools through a standardized interface

### Included Tool Examples

The repository includes several example MCP tools:

- **StockFlow**: Financial data and stock market analysis tools
- **OptionsFlow**: Options trading analysis and strategy evaluation
- **CodeSavant**: Code management, editing, and execution tools
- **StockScreen**: Stock screening and filtering capabilities

## Installation

### Prerequisites

- Python 3.10+
- Required Python packages (see `requirements.txt`)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/your-username/mcp-codex.git
cd mcp-codex
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create required directories:
```bash
mkdir -p config data logs tools
```

4. Configure your environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Usage

### Starting the Codex Service

```bash
python codex-serv.py
```

### Starting the MCP Client

```bash
python mcp-codex.py
```

### Using with Claude Desktop

1. Install the MCP Client in Claude Desktop:
```bash
mcp install mcp-codex.py
```

2. The client will register two tools:
   - `search`: Find relevant tools for your task
   - `call_tool`: Execute discovered tools

3. Example usage in Claude:
```
I need to analyze stock data for Apple. Can you help me find the right tool?
```

## Roadmap

The project was planned to include several fully-realized components:

### The Librarian (In-Depth)

The Librarian was envisioned as a sophisticated AI-powered tool orchestration system that would:

- **Function as an Agentic RAG System**: Combining retrieval capabilities with generative intelligence
- **Maintain Multiple Knowledge Sources**:
  - Industry knowledge vector database (general technical information)
  - Internal documentation vector database (specific tool capabilities)
  - Real-time MCP repository indexing (available tools in the ecosystem)
- **Execute Complex Tool Selection Logic**:
  - Analyze user queries for underlying intent
  - Match intent to required capabilities
  - Identify optimal tools across the entire MCP ecosystem
  - Consider tool compatibility, performance, and reliability
- **Provide Just-in-Time Tool Management**:
  - Detect when required tools aren't installed
  - Automatically install needed tools from repositories
  - Configure tools appropriately for the specific task
  - Verify successful installation before execution
- **Handle the Full Execution Lifecycle**:
  - Prepare tools with appropriate context
  - Monitor execution progress
  - Manage error handling and recovery
  - Provide results in the most useful format
- **Learn and Improve Continuously**:
  - Track tool performance and reliability
  - Learn from user feedback and corrections
  - Improve recommendations based on historical success
  - Adapt to new tools and capabilities

### Additional Planned Features

- User authentication and authorization
- Tool sandboxing for security
- Cloud deployment support
- Tool versioning and compatibility checking
- Performance monitoring and analytics

## Documentation

### Tool Registry Configuration

Tools are defined in the `config/codex.yaml` file with the following structure:

```yaml
tools:
  - name: tool_name
    description: Tool description
    server: path/to/tool/server.py
    methods:
      - method_name
    schemas:
      method_name:
        type: object
        properties:
          # Parameter definitions
```

### API Endpoints

The Codex service provides the following REST endpoints:

- `/health`: Health check endpoint
- `/search`: Search for tools matching a query
- `/call_tool`: Execute a specific tool method
- `/reload`: Reload tool configurations

## Why This Project

This project was created to address several limitations in the current AI tool ecosystem:

1. **Enable True Agent Capabilities**: Allow AI assistants to dynamically discover and use tools based on user needs
2. **Reduce Operational Complexity**: Eliminate the need to restart AI services when adding new capabilities
3. **Centralize Tool Management**: Provide a single point of control for tool deployment and updates
4. **Standardize Tool Interaction**: Create a consistent interface for tool discovery and execution
5. **Support Remote Execution**: Allow tools to run anywhere, not just on the local machine

Unfortunately, similar functionality was recently released by Cloudflare, making aspects of this project redundant. However, the codebase still provides valuable insights into MCP orchestration and dynamic tool discovery.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io) for the inspiration and core protocol design
- The open-source MCP community for their valuable contributions
