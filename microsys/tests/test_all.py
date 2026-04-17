"""
Test runner that executes all microsys test modules independently.
Run this file to run all tests at once.
"""
import subprocess
import sys
import os

def run_test_file(test_file):
    """Run a single test file and return the exit code."""
    print(f"\n{'='*70}")
    print(f"Running {test_file}...")
    print('='*70)
    
    result = subprocess.run(
        [sys.executable, test_file],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=False
    )
    
    return result.returncode


def run_all_tests():
    """Run all microsys test files independently."""
    test_dir = os.path.dirname(__file__)
    test_files = [
        'test_models.py',
        'test_views.py',
        'test_api.py',
        'test_middleware.py',
        'test_signals.py',
        'test_utils.py',
        'test_context_processors.py',
        'test_scaffold.py',
    ]
    
    print("="*70)
    print("Running all microsys test files...")
    print("="*70)
    
    results = {}
    for test_file in test_files:
        test_path = os.path.join(test_dir, test_file)
        exit_code = run_test_file(test_path)
        results[test_file] = exit_code
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for code in results.values() if code == 0)
    failed = len(results) - passed
    
    for test_file, exit_code in results.items():
        status = "✓ PASSED" if exit_code == 0 else "✗ FAILED"
        print(f"{status}: {test_file}")
    
    print("="*70)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    print("="*70)
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
