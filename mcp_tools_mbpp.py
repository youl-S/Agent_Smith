import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mbpp-tools")


@mcp.tool()
def run_tests(
    code: str,
    test_list: list[str],
    test_imports: list[str],
) -> str:
    """Run candidate Python code against a list of assert-based tests.
·
    Args:
        code: The candidate solution, a complete Python function
            definition (e.g. "def sub_list(a, b): return ...").
        test_list: Assert statements to check, each as a string
            (e.g. "assert sub_list([1,2],[3,4])==[-2,-2]").
        test_imports: Import statements the tests need, each as a string
            (e.g. "import math"). May be empty.

    Returns:
        A text report. "PASS: N/N tests passed" if all asserts hold,
        otherwise "FAIL: P/N tests passed" followed by the failing tests
        (FAILED for a wrong result, ERROR for code that raised).
    """
    namespace: dict = {}

    try:
        if test_imports:
            exec("\n".join(test_imports), namespace)
        exec(code, namespace)
    except Exception as e:
        return (
            f"FAIL: candidate code does not run -> " f"{type(e).__name__}: {e}"
        )

    total = len(test_list)
    passed = 0
    failures: list[str] = []

    for i, assert_str in enumerate(test_list, start=1):
        try:
            exec(assert_str, namespace)
            passed += 1
        except AssertionError:
            failures.append(f"  test {i} FAILED: {assert_str}")
        except Exception as e:
            failures.append(
                f"  test {i} ERROR: {assert_str} -> "
                f"{type(e).__name__}: {e}"
            )

    if passed == total:
        return f"PASS: {passed}/{total} tests passed"

    report = [f"FAIL: {passed}/{total} tests passed"]
    report.extend(failures)
    return "\n".join(report)


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
