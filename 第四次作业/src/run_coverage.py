"""运行单元测试并生成 coverage 覆盖率报告。"""

import os
import subprocess
import sys


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(base_dir, "test_sliding_window_max.py")
    html_dir = os.path.join(base_dir, "..", "my_coverage_result")

    print("=" * 60)
    print("1. 运行 coverage + unittest")
    print("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "coverage", "run", test_file],
        cwd=base_dir,
        check=True,
    )

    print("\n" + "=" * 60)
    print("2. 终端覆盖率摘要（语句覆盖率）")
    print("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "coverage", "report", "-m"],
        cwd=base_dir,
        check=True,
    )

    print("\n" + "=" * 60)
    print("3. 生成 HTML 报告")
    print("=" * 60)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "html",
            "-d",
            html_dir,
            "--include=sliding_window_max.py,sliding_window_max_naive.py",
        ],
        cwd=base_dir,
        check=True,
    )
    print(f"HTML 报告目录: {os.path.abspath(html_dir)}")


if __name__ == "__main__":
    main()
