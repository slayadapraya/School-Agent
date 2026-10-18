#!/usr/bin/env python3
"""Launch a separate local demo with public sample logins and synthetic records."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.demo import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8140)
    args = parser.parse_args()
    run(args.port)
