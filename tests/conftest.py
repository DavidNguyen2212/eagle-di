"""
Pytest configuration for the DI project.
Sets up PYTHONPATH so tests can import from `app`.
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
