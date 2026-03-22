"""CLI argument parsing."""

import argparse
from pathlib import Path


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare project web_search/web_fetch tools vs Claude Code tools"
    )

    parser.add_argument(
        '--tool',
        choices=['web_search', 'web_fetch'],
        help='Tool to test'
    )
    parser.add_argument(
        '--query',
        help='Search query (for web_search)'
    )
    parser.add_argument(
        '--url',
        help='URL to fetch (for web_fetch)'
    )
    parser.add_argument(
        '--batch',
        type=Path,
        help='Path to batch JSON file'
    )
    parser.add_argument(
        '--repl',
        action='store_true',
        help='Interactive REPL mode'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('.'),
        help='Directory for output reports'
    )

    return parser