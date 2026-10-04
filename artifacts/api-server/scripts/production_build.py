"""Install publishing dependencies, failing closed without leaking pip output."""
from pathlib import Path
import subprocess
import sys
import tempfile


API_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = API_ROOT / "requirements.txt"

# Only fixed messages reach build logs. pip errors may contain private index
# credentials, signed URLs, or arbitrary output from a package's build scripts.
DIAGNOSTICS = (
    (
        ("no module named pip",),
        "pip is unavailable. Restore pip for the publishing Python runtime.",
    ),
    (
        ("no matching distribution", "could not find a version", "requires a different python"),
        "Check requirements.txt pins and their compatibility with the publishing Python version.",
    ),
    (
        ("resolutionimpossible", "conflicting dependencies"),
        "Resolve conflicting dependency versions in requirements.txt.",
    ),
    (
        ("certificate_verify_failed", "sslerror"),
        "Check package-index TLS certificates and trusted CA configuration; do not disable verification.",
    ),
    (
        ("connection", "timed out", "timeout", "temporary failure", "401", "403"),
        "Check package-index access, network availability, and credentials in Publishing settings.",
    ),
    (
        ("failed building wheel", "subprocess-exited-with-error", "metadata-generation-failed"),
        "Check Python compatibility and required system libraries for native package builds.",
    ),
    (
        ("permission denied", "no space left", "read-only file system"),
        "Check publishing build storage and installation-directory permissions.",
    ),
)


def report_failure(log, returncode: int) -> None:
    print(
        f"Python dependency installation failed (exit code {returncode}); build stopped. "
        "Review requirements.txt, the publishing Python runtime, and package-index settings. "
        "Raw installer output is withheld because it may contain credentials.",
        file=sys.stderr,
    )
    matches = set()
    log.seek(0)
    for line in log:
        lowered = line.lower()
        for index, (patterns, _) in enumerate(DIAGNOSTICS):
            if any(pattern in lowered for pattern in patterns):
                matches.add(index)
    for index in sorted(matches):
        print(DIAGNOSTICS[index][1], file=sys.stderr)


def main() -> int:
    try:
        # Check readability before invoking pip; never import app configuration
        # or touch a database as part of dependency installation.
        with REQUIREMENTS.open("rb"):
            pass
        print("Installing API Python dependencies from requirements.txt.", flush=True)
        # TemporaryFile is private and deleted on close; no raw log is retained.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as log:
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip", "install",
                    "--disable-pip-version-check", "--no-input",
                    "-r", str(REQUIREMENTS),
                ],
                cwd=API_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                report_failure(log, result.returncode)
                # Signals must also fail the build; retain normal pip exit codes.
                return result.returncode if 0 < result.returncode < 256 else 1
    except OSError:
        print(
            "Python dependency installation could not run; build stopped. "
            "Check requirements.txt readability, Python/pip availability, "
            "and temporary build-storage permissions.",
            file=sys.stderr,
        )
        return 1
    print("API Python dependencies installed successfully.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())