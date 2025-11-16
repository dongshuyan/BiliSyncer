"""
使用示例：

真正执行（默认删除隐藏文件）：

python flatten.py /path/to/p -n 1


只看效果，不动真实文件：

python flatten.py /path/to/p -n 1 --dry-run


扁平化第 2 层目录，同时保留所有隐藏文件，8 线程 dry-run：

python flatten.py /path/to/p -n 2 --keep-hidden --jobs 8 --dry-run
python flatten.py /Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili -n 1 --keep-hidden --jobs 8 --dry-run


如果你还想要日志输出到文件（方便审计），我也可以帮你加上 --log-file 参数。
"""
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 全局：目标目录锁表，防止并发写入同一目录时命名冲突
_dir_locks = {}
_dir_locks_lock = threading.Lock()


def get_dir_lock(directory: Path) -> threading.Lock:
    """为每个目标目录提供一把全局共享的锁，用于 safe_move。"""
    directory = directory.resolve()
    key = str(directory)
    with _dir_locks_lock:
        lock = _dir_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _dir_locks[key] = lock
    return lock


def safe_move(src: Path, target_dir: Path, dry_run: bool = False) -> None:  # NEW: dry_run
    """
    将 src 文件安全地移动到 target_dir 中：
    - 如果 src 已经在 target_dir 下，什么也不做；
    - 如有同名文件，自动生成不冲突的新名字：name__dup1.ext, name__dup2.ext, ...
    - 利用每个目录一把锁，避免并发竞态导致覆盖或命名冲突。
    """
    src = src.resolve()
    target_dir = target_dir.resolve()

    if not src.exists():
        # 文件有可能在前面的步骤中被删除或移动，记录一下即可
        logging.warning("Source file vanished before move: %s", src)
        return

    # 如果文件本来就在目标目录中，则不需要移动
    if src.parent == target_dir:
        return

    lock = get_dir_lock(target_dir)
    with lock:
        base_name = src.name
        dest = target_dir / base_name

        # 如果目标文件不存在，直接移动
        if not dest.exists():
            if dry_run:  # NEW
                logging.info("[DRY-RUN] Would move %s -> %s", src, dest)
            else:
                try:
                    shutil.move(str(src), str(dest))
                except Exception as e:
                    logging.error("Failed to move %s -> %s: %s", src, dest, e)
            return

        # 存在同名文件，尝试追加 __dupN 后缀
        stem, suffix = os.path.splitext(base_name)
        idx = 1
        while True:
            candidate = target_dir / f"{stem}__dup{idx}{suffix}"
            if not candidate.exists():
                if dry_run:  # NEW
                    logging.info("[DRY-RUN] Would move %s -> %s", src, candidate)
                else:
                    try:
                        shutil.move(str(src), str(candidate))
                    except Exception as e:
                        logging.error("Failed to move %s -> %s: %s", src, candidate, e)
                return
            idx += 1


def flatten_all_into(
    root_dir: Path,
    executor: ThreadPoolExecutor,
    delete_hidden: bool,
    dry_run: bool = False,  # NEW
) -> None:
    """
    将 root_dir 子树下所有非隐藏文件移动到 root_dir 下，并尽可能删除其下所有子目录。
    delete_hidden=True 时，会删除遍历到的所有以 "." 开头的普通文件。
    隐藏目录（名字以 "." 开头）会整个跳过，不进行任何操作。

    dry_run=True 时不会做任何实际的移动 / 删除，只打印将要进行的操作。
    """
    root_dir = root_dir.resolve()
    logging.info(
        "Flattening subtree into: %s%s",
        root_dir,
        " (DRY-RUN)" if dry_run else "",
    )

    files_to_move = []
    hidden_files_to_delete = []
    all_dirs = []

    # 1. 扫描阶段：只记录，不修改
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True, followlinks=False):
        current_dir = Path(dirpath)

        # 跳过隐藏目录（以 "." 开头），保证 .git 等不会被破坏
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        # 记录子目录（后续尝试删除）
        if current_dir != root_dir:
            all_dirs.append(current_dir)

        # 处理当前目录中的文件
        for name in filenames:
            file_path = current_dir / name

            # 隐藏文件处理
            if name.startswith("."):
                if delete_hidden:
                    hidden_files_to_delete.append(file_path)
                # 无论是否删除隐藏文件，都不把其加入移动列表
                continue

            # 非隐藏文件：如果不在 root_dir 本身，就需要移动到 root_dir
            if current_dir != root_dir:
                files_to_move.append(file_path)

    # 2. 删除隐藏文件
    if delete_hidden and hidden_files_to_delete:
        logging.info(
            "%sDeleting %d hidden files under %s",
            "[DRY-RUN] " if dry_run else "",
            len(hidden_files_to_delete),
            root_dir,
        )
        for fpath in hidden_files_to_delete:
            if dry_run:
                logging.info("[DRY-RUN] Would delete hidden file %s", fpath)
            else:
                try:
                    if fpath.exists():
                        fpath.unlink()
                except Exception as e:
                    logging.error("Failed to delete hidden file %s: %s", fpath, e)

    # 3. 并行移动文件
    if files_to_move:
        logging.info(
            "%sMoving %d files into %s",
            "[DRY-RUN] " if dry_run else "",
            len(files_to_move),
            root_dir,
        )
        futures = [executor.submit(safe_move, src, root_dir, dry_run) for src in files_to_move]
        for fut in as_completed(futures):
            exc = fut.exception()
            if exc:
                logging.error("Error during moving files: %s", exc)

    # 4. 自底向上删除子目录
    if all_dirs:
        # 按深度从大到小排序
        all_dirs.sort(key=lambda d: len(d.relative_to(root_dir).parts), reverse=True)
        for d in all_dirs:
            if dry_run:
                logging.info("[DRY-RUN] Would remove directory: %s", d)
                continue
            try:
                d.rmdir()
                logging.info("Removed directory: %s", d)
            except OSError as e:
                # 目录非空或无权限等，不强行处理，记录一下信息
                logging.debug("Directory not removed (not empty or permission denied): %s (%s)", d, e)


def collect_target_dirs(root: Path, level: int):
    """
    收集相对于 root 深度为 level 的所有目录。
    level == 0 时只包含 root 自身。
    会跳过以 "." 开头的目录。
    """
    root = root.resolve()
    if level == 0:
        return [root]

    result = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)

        # 跳过隐藏目录
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        if current == root:
            rel_depth = 0
        else:
            rel_depth = len(current.relative_to(root).parts)

        if rel_depth == level:
            result.append(current)
            # 不再深入此子树，因为更深的目录不会是目标
            dirnames[:] = []

    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "将指定目录树在第 n 层进行扁平化："
            "把所有深度为 n 的目录的子树文件集中到该目录下，并删除其下子目录。"
        )
    )
    parser.add_argument(
        "path",
        help="要处理的根目录路径 p",
    )
    parser.add_argument(
        "-n",
        "--level",
        type=int,
        default=0,
        help="要扁平化的层级 n（相对于 p，p 的深度为 0），默认 0",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=8,
        help="最大并行线程数，默认 8",
    )

    hidden_group = parser.add_mutually_exclusive_group()
    hidden_group.add_argument(
        "--delete-hidden",
        dest="delete_hidden",
        action="store_true",
        help="删除所有以 '.' 开头的隐藏文件（默认行为）",
    )
    hidden_group.add_argument(
        "--keep-hidden",
        dest="delete_hidden",
        action="store_false",
        help="保留以 '.' 开头的隐藏文件（不删除）",
    )
    parser.set_defaults(delete_hidden=True)

    parser.add_argument(  # NEW
        "--dry-run",
        action="store_true",
        help="仅打印将要执行的操作，不实际移动/删除任何文件或目录",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # 初始化日志
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    root = Path(args.path).expanduser().resolve()

    if not root.exists():
        logging.error("Path does not exist: %s", root)
        return

    if not root.is_dir():
        logging.error("Path is not a directory: %s", root)
        return

    if args.level < 0:
        logging.error("Level n must be >= 0, got %d", args.level)
        return

    jobs = max(1, args.jobs)

    # 收集所有深度为 n 的目标目录
    target_dirs = collect_target_dirs(root, args.level)
    if not target_dirs:
        logging.info("No directories found at level %d under %s. Nothing to do.", args.level, root)
        return

    logging.info(
        "Found %d target directories at level %d under %s%s",
        len(target_dirs),
        args.level,
        root,
        " (DRY-RUN)" if args.dry_run else "",
    )

    # 全局线程池，用于所有文件移动任务
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for d in target_dirs:
            flatten_all_into(d, executor, args.delete_hidden, args.dry_run)

    logging.info("Done%s", " (DRY-RUN)" if args.dry_run else "")


if __name__ == "__main__":
    main()
