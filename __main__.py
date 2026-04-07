#!/usr/bin/env python3
"""
Entry point for running OPC as a module: python -m opc_optimizer

This module enables the following execution modes:
    python -m opc_optimizer [options]
    python -m opc_optimizer --web-ui

The main() function from main.py is called to handle all CLI arguments
and start the optimization workflow.

Supported CLI Arguments:
    --web-ui               Launch Minecraft-style 3D Web UI in browser
    --goal GOAL            Set the primary optimization goal
    --max-rounds N         Maximum number of optimization rounds
    --archive-every N      Archive historical data every N rounds
    --dry-run              Preview changes without modifying files
    --auto                 Automated mode without user interaction
    --resume               Resume from last checkpoint
    --model MODEL          Default LLM model (e.g. openai/gpt-4o)
    --timeout SECONDS      LLM call timeout in seconds
    --http-port PORT       Preferred HTTP port for Web UI
    --formatter CMD        Explicit formatter command
    --no-format            Disable auto-formatting after modifications
"""

from .main import main

if __name__ == "__main__":
    main()
