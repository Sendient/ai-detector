import subprocess
import os
import sys

def main():
    script_path = os.path.join(os.path.dirname(__file__), "scripts", "run_tests.sh")

    if not os.path.isfile(script_path):
        print(f"Test runner script not found: {script_path}")
        sys.exit(1)

    # Define required environment variables inline
    env = os.environ.copy()
    env["MONGODB_URL"] = "mongodb://localhost:27017/testdb"
    env["KINDE_DOMAIN"] = "dummy.kinde.com"
    env["KINDE_AUDIENCE"] = "dummy-audience"

    try:
        subprocess.run(["bash", script_path], check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Test script failed with return code {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
