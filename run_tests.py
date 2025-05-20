import sys
import os
import glob

# Add the vendor wheel packages to sys.path
wheel_dir = os.path.abspath("vendor")
for wheel in glob.glob(os.path.join(wheel_dir, "*.whl")):
    sys.path.insert(0, wheel)

# Try importing pytest after extending path
try:
    import pytest
except ImportError as e:
    print("❌ Pytest could not be imported. Check if all required packages were vendored.")
    raise e

# Run pytest
sys.exit(pytest.main(["-q"]))
