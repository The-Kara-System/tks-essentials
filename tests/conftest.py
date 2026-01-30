import os
import tempfile
from pathlib import Path


PROJECT_ROOT = os.environ.get("PROJECT_ROOT")
if PROJECT_ROOT is None:
    temp_root = Path(tempfile.mkdtemp(prefix="tksessentials_tests_"))
    os.environ["PROJECT_ROOT"] = str(temp_root)
