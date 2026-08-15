#!/usr/bin/env python3
"""Call one Serena MCP tool over stdio and print its JSON result.

Serena has no query CLI -- it is an MCP server -- so the facade speaks the
protocol directly rather than shelling out to an agent.

Usage: serena_call.py <project-dir> <tool-name> [json-args]
"""
import json
import subprocess
import sys
import threading

SERENA = ["uvx", "--from", "git+https://github.com/oraios/serena", "serena",
          "start-mcp-server", "--transport", "stdio", "--enable-web-dashboard", "false"]


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    project, tool = sys.argv[1], sys.argv[2]
    args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

    proc = subprocess.Popen(
        SERENA + ["--project", project],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def read_until(match_id, timeout=300):
        box = {}

        def reader():
            for line in proc.stdout:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == match_id:
                    box["msg"] = msg
                    return

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout)
        return box.get("msg")

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "cs-facade", "version": "1"}}})
    if not read_until(1):
        print("serena: initialize timed out", file=sys.stderr)
        proc.terminate()
        return 1
    send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": tool, "arguments": args}})
    res = read_until(2)
    proc.terminate()

    if not res:
        print("serena: call timed out", file=sys.stderr)
        return 1
    if "error" in res:
        print("serena: " + json.dumps(res["error"])[:300], file=sys.stderr)
        return 1

    for item in res.get("result", {}).get("content", []):
        print(item.get("text", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
