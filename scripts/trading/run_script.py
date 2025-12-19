#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / '..' / 'src'))

script_path = sys.argv[1] if len(sys.argv) > 1 else None
if script_path and Path(script_path).exists():
    # Copy config if missing
    config_dir = Path(script_path).parent
    if not (config_dir / 'config.yml').exists():
        (config_dir / 'config.yml').write_bytes(Path('../config.yml').read_bytes())
    
    # Run script
    exec(open(script_path).read())
else:
    print("Usage: python3 run_script.py <script.py>")
