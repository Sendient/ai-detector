import sys
import os

VENDOR_DIR = os.path.abspath("vendor_packages")
if not os.path.isdir(VENDOR_DIR):
    print("❌ vendor_packages not found")
    sys.exit(1)

# Prepend vendor_packages to ensure they override system packages
sys.path.insert(0, VENDOR_DIR)

# Append each subfolder (like 'fitz', 'cryptography', etc.)
for entry in os.listdir(VENDOR_DIR):
    full_path = os.path.join(VENDOR_DIR, entry)
    if os.path.isdir(full_path):
        sys.path.insert(0, full_path)

# Force-load pymupdf as a proper package if necessary
if "pymupdf" not in sys.modules:
    import importlib.util
    pymupdf_path = os.path.join(VENDOR_DIR, "pymupdf", "pymupdf.py")
    if os.path.exists(pymupdf_path):
        spec = importlib.util.spec_from_file_location("pymupdf.pymupdf", pymupdf_path)
        pymupdf = importlib.util.module_from_spec(spec)
        sys.modules["pymupdf"] = pymupdf
        spec.loader.exec_module(pymupdf)

# Ensure multipart is available
multipart_path = os.path.join(VENDOR_DIR, "multipart")
if os.path.isdir(multipart_path):
    sys.path.insert(0, multipart_path)

try:
    import multipart
    print(f"✅ multipart loaded from: {multipart.__file__}")
except Exception as e:
    print(f"❌ multipart import failed: {e}")

try:
    import fitz
    print(f"✅ fitz loaded from: {fitz.__file__}")
except Exception as e:
    print(f"❌ fitz import failed: {e}")

try:
    import pytest
except ImportError:
    print("❌ pytest not found in vendor_packages")
    raise

print("🚀 Running test suite...\n")
sys.exit(pytest.main(["-q"]))
