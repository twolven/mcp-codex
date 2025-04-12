import subprocess
import json
import sys
import time
import threading
from queue import Queue, Empty

def read_output(pipe, queue):
    try:
        for line in pipe:
            queue.put(line)
    except:
        pass

def wait_for_message(queue, timeout=10, condition=None):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            msg = queue.get(timeout=0.1)
            try:
                data = json.loads(msg)
                if condition is None or condition(data):
                    return data
                queue.put(msg)
            except json.JSONDecodeError:
                print(f"Invalid JSON: {msg}", file=sys.stderr)
        except Empty:
            continue
    return None

def run_tool_request(tool_name: str, params: dict):
    print("\n=== Starting Request ===", file=sys.stderr)
    
    print("1. Launching stockflow.py...", file=sys.stderr)
    process = subprocess.Popen(
        ['python', 'stockflow.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    stdout_queue = Queue()
    stderr_queue = Queue()
    
    stdout_thread = threading.Thread(target=read_output, args=(process.stdout, stdout_queue))
    stderr_thread = threading.Thread(target=read_output, args=(process.stderr, stderr_queue))
    
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    
    stdout_thread.start()
    stderr_thread.start()

    try:
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "python-mcp-client",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {
                        "listChanged": False
                    }
                }
            }
        }
        
        print(f"2. Sending initialize: {json.dumps(init_request)}", file=sys.stderr)
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        # Wait for initialize response
        print("3. Waiting for initialize response...", file=sys.stderr)
        init_response = wait_for_message(stdout_queue, 
                                       condition=lambda x: x.get("id") == 1)
        if not init_response:
            print("Initialize response timeout!", file=sys.stderr)
            return None
            
        print(f"Initialize response: {json.dumps(init_response)}", file=sys.stderr)
        
        # Print any stderr messages
        while not stderr_queue.empty():
            stderr_msg = stderr_queue.get().strip()
            print(f"Server stderr: {stderr_msg}", file=sys.stderr)
        
        # Send initialized notification with correct format
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",  # Correct method name
            "params": {
                "progressToken": "init",  # Required field
                "progress": {            # Required field
                    "kind": "begin"
                }
            }
        }
        
        print(f"4. Sending initialized notification: {json.dumps(initialized_notification)}", file=sys.stderr)
        process.stdin.write(json.dumps(initialized_notification) + "\n")
        process.stdin.flush()
        
        # Give the server a moment to process
        time.sleep(1)
        
        # Now send the tool request
        tool_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params
            }
        }
        
        print(f"\n5. Sending tool request: {json.dumps(tool_request)}", file=sys.stderr)
        process.stdin.write(json.dumps(tool_request) + "\n")
        process.stdin.flush()
        
        # Wait for tool response while monitoring stderr
        print("6. Waiting for tool response...", file=sys.stderr)
        tool_response = wait_for_message(stdout_queue, 
                                       timeout=30,
                                       condition=lambda x: x.get("id") == 2)
        
        # Print any stderr messages
        while not stderr_queue.empty():
            stderr_msg = stderr_queue.get().strip()
            print(f"Server stderr: {stderr_msg}", file=sys.stderr)
        
        if tool_response:
            print(f"Tool response received: {json.dumps(tool_response)}", file=sys.stderr)
            return tool_response
        else:
            print("Tool response timeout!", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return None
    finally:
        print("\n7. Cleaning up...", file=sys.stderr)
        if process.poll() is None:
            process.terminate()
            time.sleep(0.5)
            if process.poll() is None:
                process.kill()
        
        while not stderr_queue.empty():
            stderr_msg = stderr_queue.get().strip()
            print(f"Final stderr: {stderr_msg}", file=sys.stderr)
            
        print("=== End Request ===\n", file=sys.stderr)

if __name__ == "__main__":
    print("Testing MCP communication...", file=sys.stderr)
    result = run_tool_request("get_stock_data_v2", {
        "symbol": "AAPL",
        "include_financials": False,
        "include_analysis": False,
        "include_calendar": False
    })
    
    if result:
        print("\nResult:", json.dumps(result, indent=2))
    else:
        print("\nNo result received!")