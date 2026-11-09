"""
Capri Test Suite Package
Configures root path so all test modules can import abilities, brain, config, etc. seamlessly.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
