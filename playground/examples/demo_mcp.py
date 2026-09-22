#!/usr/bin/env python3
"""Starts the playground's demo MCP server on stdio: python3 demo_mcp.py [--vulnerable]."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiplayground import demo  # noqa: E402

demo.serve_mcp_stdio(vulnerable="--vulnerable" in sys.argv)
