#!/usr/bin/env python3
"""Compatibility wrapper for the active v3.1 scenario validator.

The historical script name is retained because earlier review bundles pointed
to it. It now validates `scenarios_v3_1` by default via validate_scenarios.py.
"""

from validate_scenarios import main


if __name__ == "__main__":
    raise SystemExit(main())
