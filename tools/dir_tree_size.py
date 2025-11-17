#!/usr/bin/env python3
"""
目录占用分析工具：以 tree 风格输出每个子目录/文件的大小
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime


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


def check_leaf_directory(dir_path: Path) -> Dict[str, bool]:
    """检查叶子目录（最底层目录）中的mp4和m4s文件情况
    
    Returns:
        Dict with keys: 'has_mp4', 'has_m4s'
    """
    has_mp4 = False
    has_m4s = False
    
    try:
        for item in dir_path.iterdir():
            if item.is_file():
                name_lower = item.name.lower()
                if name_lower.endswith('.mp4'):
                    has_mp4 = True
                elif name_lower.endswith('.m4s'):
                    has_m4s = True
    except (PermissionError, OSError):
        pass
    
    return {'has_mp4': has_mp4, 'has_m4s': has_m4s}


def scan_directory(path: Path, leaf_issues: List[Dict[str, str]] = None) -> Tuple[int, List[Entry]]:
    """递归统计目录大小并返回子项信息
    
    Args:
        path: 要扫描的目录路径
        leaf_issues: 用于收集叶子目录问题的列表
    
    Returns:
        Tuple of (total_size, entries)
    """
    if leaf_issues is None:
        leaf_issues = []
    
    total_size = 0
    entries: List[Entry] = []
    has_subdirs = False
    
    try:
        items = list(path.iterdir())
    except PermissionError:
        return 0, []
    
    for item in items:
        try:
            if item.is_symlink():
                continue
            if item.is_dir():
                has_subdirs = True
                child_size, child_entries = scan_directory(item, leaf_issues)
                entries.append(("dir", item.name, child_size, child_entries))
                total_size += child_size
            else:
                size = item.stat().st_size
                entries.append(("file", item.name, size, None))
                total_size += size
        except (PermissionError, OSError):
            continue
    
    # 检查叶子目录（没有子目录的目录）
    if not has_subdirs and entries:
        # 检查这个目录是否是叶子目录（只有文件，没有子目录）
        has_any_subdir = any(entry[0] == "dir" for entry in entries)
        if not has_any_subdir:
            check_result = check_leaf_directory(path)
            issues = []
            if not check_result['has_mp4']:
                issues.append("缺少mp4文件")
            if check_result['has_m4s']:
                issues.append("存在m4s文件")
            
            if issues:
                leaf_issues.append({
                    'path': str(path),
                    'issues': issues
                })
    
    # 按照占用空间从小到大排序
    entries.sort(key=lambda x: x[2])  # x[2] 是 size
    
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


def generate_log_file(target_dir: Path, leaf_issues: List[Dict[str, str]]) -> Optional[Path]:
    """生成日志文件，记录叶子目录的问题"""
    if not leaf_issues:
        return None
    
    # 生成日志文件名：目录名_检查报告_时间戳.log，保存在被检查的目录中
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"{target_dir.name}_检查报告_{timestamp}.log"
    log_path = target_dir / log_filename
    
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"目录检查报告\n")
        f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"检查目录: {target_dir}\n")
        f.write(f"=" * 80 + "\n\n")
        f.write(f"发现 {len(leaf_issues)} 个叶子目录存在问题：\n\n")
        
        for idx, issue_info in enumerate(leaf_issues, 1):
            f.write(f"{idx}. {issue_info['path']}\n")
            f.write(f"   问题: {', '.join(issue_info['issues'])}\n\n")
        
        # 统计信息
        f.write("=" * 80 + "\n")
        f.write("统计信息：\n\n")
        
        no_mp4_count = sum(1 for issue in leaf_issues if "缺少mp4文件" in issue['issues'])
        has_m4s_count = sum(1 for issue in leaf_issues if "存在m4s文件" in issue['issues'])
        both_count = sum(1 for issue in leaf_issues if len(issue['issues']) == 2)
        
        f.write(f"缺少mp4文件的目录: {no_mp4_count} 个\n")
        f.write(f"存在m4s文件的目录: {has_m4s_count} 个\n")
        f.write(f"同时存在两种问题的目录: {both_count} 个\n")
    
    return log_path


def parse_args() -> Tuple[Path, bool]:
    parser = argparse.ArgumentParser(description="目录占用分析工具（tree 格式输出）")
    parser.add_argument("directory", help="需要分析的目录路径")
    parser.add_argument("--no-check", action="store_true", help="不检查叶子目录的mp4/m4s文件")
    args = parser.parse_args()
    target = Path(args.directory).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"目录不存在: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"不是有效目录: {target}")
    return target, not args.no_check


def main() -> None:
    target_dir, enable_check = parse_args()
    leaf_issues = []
    
    if enable_check:
        total, entries = scan_directory(target_dir, leaf_issues)
    else:
        total, entries = scan_directory(target_dir)
    
    print(f"{target_dir} ({format_size(total)})")
    print_tree(entries)
    
    # 生成日志文件
    if enable_check and leaf_issues:
        log_path = generate_log_file(target_dir, leaf_issues)
        if log_path:
            print(f"\n已生成检查报告: {log_path}")
            print(f"发现 {len(leaf_issues)} 个叶子目录存在问题")
    elif enable_check:
        print("\n所有叶子目录检查正常，未发现问题")


if __name__ == "__main__":
    main()
