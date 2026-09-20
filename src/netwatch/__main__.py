"""Entry point for ``python -m netwatch`` — used by the run-on-startup key."""

from netwatch.app import main

if __name__ == "__main__":
    raise SystemExit(main())
