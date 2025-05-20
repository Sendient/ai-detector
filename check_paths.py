import sys
import os

print("--- Python Environment Check ---")
print(f"sys.executable: {sys.executable}")
print("\nsys.path:")
for p in sys.path:
    print(f"  {p}")

print(f"\nPYTHONPATH environment variable: {os.getenv('PYTHONPATH')}")

print("\n--- Module Import Check ---")
try:
    import pydantic_settings
    print(f"pydantic_settings location: {pydantic_settings.__file__}")
except ImportError as e:
    print(f"pydantic_settings: NOT FOUND ({e})")

try:
    import pytest_httpx
    print(f"pytest_httpx location: {pytest_httpx.__file__}")
except ImportError as e:
    print(f"pytest_httpx: NOT FOUND ({e})")

try:
    import pytest_asyncio
    print(f"pytest_asyncio location: {pytest_asyncio.__file__}")
except ImportError as e:
    print(f"pytest_asyncio: NOT FOUND ({e})")

print("-----------------------------") 