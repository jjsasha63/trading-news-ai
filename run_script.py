#!/usr/bin/env python3
import sys
import os
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python3 run_script.py <script.py>")
    sys.exit(1)

script_path = sys.argv[1]
script_path = Path(script_path).resolve()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Copy config.yml if missing
config_dir = script_path.parent
config_file = config_dir / 'config.yml'
if not config_file.exists():
    project_config = Path(__file__).parent / 'config.yml'
    config_file.write_bytes(project_config.read_bytes())
    print(f"📋 Copied config.yml to {config_dir}")

# Run script
print(f"🚀 Running {script_path}")
exec(open(script_path).read())
