#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from suite_runtime import cli_check

if __name__ == "__main__":
    cli_check(ROOT)
