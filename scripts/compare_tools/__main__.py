"""CLI entry point."""

import sys

from scripts.compare_tools.cli import create_parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Import main after args are parsed to avoid circular imports
    from scripts.compare_tools.main import run

    sys.exit(run(args))