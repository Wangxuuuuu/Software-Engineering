"""Pylint 静态代码分析脚本，生成详细报告。"""

import os
import sys

import pylint.lint


def run_pylint(target_files: list) -> None:
    """对指定 Python 文件运行 pylint 并输出详细报告。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    rcfile = os.path.join(base_dir, ".pylintrc")
    options = ["-ry", f"--rcfile={rcfile}"] + target_files
    pylint.lint.Run(options)


def main() -> None:
    """分析主程序与原始代码文件。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    targets = [
        os.path.join(base_dir, "sliding_window_max.py"),
        os.path.join(base_dir, "sliding_window_max_naive.py"),
    ]
    run_pylint(targets)


if __name__ == "__main__":
    main()
