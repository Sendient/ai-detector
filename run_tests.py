import sys
import os

# Ensure the vendored packages directory is available
VENDOR_DIR = os.path.abspath("vendor_packages")
if not os.path.isdir(VENDOR_DIR):
    print(f"❌ Vendor directory not found: {VENDOR_DIR}")
    sys.exit(1)

# Add the extracted packages to sys.path
sys.path.insert(0, VENDOR_DIR)

# Confirm for debugging
print(f"✅ sys.path updated to include: {VENDOR_DIR}")

# Try importing pytest
try:
    import pytest
except ImportError as e:
    print("❌ Failed to import pytest. Make sure it is extracted to vendor_packages.")
    raise e

# Run pytest with quiet output
print("🚀 Running test suite with pytest...\n")
exit_code = pytest.main(["-q"])
sys.exit(exit_code)
