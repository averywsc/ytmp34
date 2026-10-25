import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "server" / "requirements.txt"
BACKEND = ROOT / "server" / "app.py"
DEPENDENCIES = {
    "flask": "flask",
    "yt_dlp": "yt-dlp",
}


def install_missing_dependencies():
    missing = [
        package
        for module, package in DEPENDENCIES.items()
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        return

    print(f"Installing missing dependencies: {', '.join(missing)}", flush=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=ROOT,
        check=True,
    )


def main():
    if not REQUIREMENTS.is_file():
        raise FileNotFoundError(f"Dependency file not found: {REQUIREMENTS}")
    if not BACKEND.is_file():
        raise FileNotFoundError(f"Backend file not found: {BACKEND}")

    install_missing_dependencies()
    print("Open http://127.0.0.1:5000 in your browser.", flush=True)
    print("Keep this window open while you use the converter.", flush=True)
    process = subprocess.Popen(
        [sys.executable, str(BACKEND)],
        cwd=ROOT,
    )
    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping the application...", flush=True)
        if process.poll() is None:
            process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
