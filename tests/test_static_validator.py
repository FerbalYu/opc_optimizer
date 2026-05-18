from utils.static_validator import is_env_error


def test_pytest_assertion_failure_is_not_env_error():
    output = """
[test] exit_code=1
FAILED tests/test_stats_tool.py::test_average_empty_returns_zero - AssertionError
=========================== short test summary info ===========================
1 failed in 0.20s
"""

    assert is_env_error(output) is False


def test_python_runtime_failure_is_not_env_error():
    output = """
[test] exit_code=1
Traceback (most recent call last):
  File "stats_tool.py", line 10, in <module>
IndexError: list index out of range
"""

    assert is_env_error(output) is False


def test_missing_pytest_is_env_error():
    output = "[test] exit_code=1\nNo module named pytest"

    assert is_env_error(output) is True


def test_command_not_found_is_env_error():
    output = "[test] command not found: pytest"

    assert is_env_error(output) is True
