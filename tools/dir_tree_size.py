#!/usr/bin/env python3
"""
目录占用分析工具：以 tree 风格输出每个子目录/文件的大小
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple, Optional


Entry = Tuple[str, str, int, Optional[List["Entry"]]]


def format_size(size_bytes: int) -> str:
    """将字节数转换为易读格式"""
    if size_bytes <= 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:.2f} {units[idx]}"


def scan_directory(path: Path) -> Tuple[int, List[Entry]]:
    """递归统计目录大小并返回子项信息"""
    total_size = 0
    entries: List[Entry] = []
    
    try:
        items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return 0, []
    
    for item in items:
        try:
            if item.is_symlink():
                continue
            if item.is_dir():
                child_size, child_entries = scan_directory(item)
                entries.append(("dir", item.name, child_size, child_entries))
                total_size += child_size
            else:
                size = item.stat().st_size
                entries.append(("file", item.name, size, None))
                total_size += size
        except (PermissionError, OSError):
            continue
    
    return total_size, entries


def print_tree(entries: List[Entry], prefix: str = "") -> None:
    """以 tree 风格打印目录树"""
    for idx, (entry_type, name, size, children) in enumerate(entries):
        is_last = idx == len(entries) - 1
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{name} ({format_size(size)})")
        if children is not None:
            next_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(children, next_prefix)


def parse_args() -> Path:
    parser = argparse.ArgumentParser(description="目录占用分析工具（tree 格式输出）")
    parser.add_argument("directory", help="需要分析的目录路径")
    args = parser.parse_args()
    target = Path(args.directory).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"目录不存在: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"不是有效目录: {target}")
    return target


def main() -> None:
    target_dir = parse_args()
    total, entries = scan_directory(target_dir)
    print(f"{target_dir} ({format_size(total)})")
    print_tree(entries)


if __name__ == "__main__":
    main()
