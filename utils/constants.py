"""Constants for OPC Local Optimizer.

This module centralizes all magic numbers and configuration constants
to improve code maintainability and configurability.
"""

import os

# File processing limits
MAX_FILES = 15
MAX_FILE_CONTENT_LENGTH = 4000
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "512000"))

# Token budgets
DEFAULT_TOKEN_BUDGET = 12000
MAX_TOKEN_BUDGET = 24000
DOCS_TOKEN_BUDGET = 4000

# Timeout settings (seconds)
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))
BUILD_TIMEOUT = int(os.getenv("BUILD_TIMEOUT", "120"))
ROUND_TIMEOUT = int(os.getenv("ROUND_TIMEOUT", "600"))
WEB_UI_COMMAND_TIMEOUT = int(os.getenv("WEB_UI_COMMAND_TIMEOUT", "30"))
UI_CHECK_TIMEOUT = int(os.getenv("UI_CHECK_TIMEOUT", "60"))
DEV_SERVER_START_TIMEOUT = 45

# Path/Input limits
MAX_GOAL_LENGTH = 2000
MAX_INPUT_LENGTH = 500
MAX_COMMAND_LENGTH = 150
MAX_DIFF_LINES = 100

# UI preview limits
MAX_PREVIEW_LINES = 80
MAX_DIFF_PREVIEW_LINES = 20
MAX_HISTORY_SUMMARY_LENGTH = 200

# Score ranges
MIN_SCORE = 1
MAX_SCORE = 10

# Token estimation
CHARS_PER_TOKEN_CJK = 1
CHARS_PER_TOKEN_OTHER = 4

# CLI defaults
DEFAULT_WEB_UI_HTTP_PORT = 8765
MAX_PORT_SCAN_ATTEMPTS = 100

# Dev server URLs for UI validation
DEFAULT_DEV_SERVER_URLS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]

# Plan/Execute budget limits
EXECUTE_FILES_BUDGET = 12000
EXECUTE_DOCS_BUDGET = 4000
PLAN_CONTEXT_BUDGET_MIN = 8000
PLAN_CONTEXT_BUDGET_MAX = 16000

# Arch context
MAX_ARCH_CONTEXT_FILES = 5
