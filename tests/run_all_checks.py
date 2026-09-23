"""
Runs every regression check script in this directory (check_*.py) as its own
subprocess and prints a pass/fail summary - the "run this any time you add or
change something" entry point. Each check_*.py is a standalone script (no
pytest/unittest dependency, matching this project's existing convention) that
exits non-zero and prints a traceback on failure, zero and a final "PASSED: "
line on success - this runner just aggregates that.

When adding a new feature, add a new check_<feature>.py alongside the
existing ones (same pattern: plain functions, real objects, real asserts, a
final PASSED line) rather than bolting more checks onto an unrelated file -
this runner picks up any check_*.py automatically, no registration needed.

Run with: .venv\\Scripts\\python.exe tests\\run_all_checks.py
"""
import glob
import os
import subprocess
import sys
import time

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def main():
    scripts = sorted(
        p for p in glob.glob(os.path.join(TESTS_DIR, "check_*.py"))
        if os.path.basename(p) != os.path.basename(__file__)
    )
    if not scripts:
        print("No check_*.py scripts found under tests/.")
        return 1

    results = []
    for path in scripts:
        name = os.path.basename(path)
        print(f"\n=== {name} " + "=" * max(1, 60 - len(name)))
        t0 = time.time()
        proc = subprocess.run([PYTHON, path], cwd=TESTS_DIR, capture_output=True, text=True)
        dt = time.time() - t0
        ok = proc.returncode == 0
        results.append((name, ok, dt))
        # always show the script's own output - its per-check PASSED lines (or
        # the traceback on failure) are the actual evidence, not just ok/fail
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        print(f"--- {name}: {'PASSED' if ok else 'FAILED'} ({dt:.1f}s)")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, ok, dt in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({dt:.1f}s)")
    failed = [n for n, ok, _ in results if not ok]
    total = len(results)
    print(f"\n{total - len(failed)}/{total} check scripts passed.")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("PASSED: every regression check script is green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
