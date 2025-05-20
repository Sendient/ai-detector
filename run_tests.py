import sys
import os

# Add extracted vendor packages to the path
VENDOR_DIR = os.path.abspath("vendor_packages")
if not os.path.isdir(VENDOR_DIR):
    print(f"❌ Vendor directory not found: {VENDOR_DIR}")
    sys.exit(1)

sys.path.insert(0, VENDOR_DIR)
print(f"✅ sys.path updated to include: {VENDOR_DIR}")

try:
    import pytest
except ImportError:
    print("❌ Pytest not found in vendor packages")
    raise

print("🚀 Running test suite with pytest...\n")
sys.exit(pytest.main(["-q"]))
