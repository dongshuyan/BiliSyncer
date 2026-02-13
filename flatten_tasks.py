#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 BiliSyncer 任务目录结构的专用“拍平”脚本。

使用场景（与你描述的一致）：

1. 你给脚本一个“起始路径”，例如：
   - 单个任务目录：
     /Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili/UP主-419524011-珍珠小鱼了
   - 或者更上层的目录：
     /Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili

2. 脚本会自动识别“当前仓库下载出来的任务目录”，也就是
   utils/constants.py 里的 TASK_FOLDER_PREFIXES 所定义的这几类前缀：
   - 投稿视频-
   - 番剧-
   - 收藏夹-
   - 视频列表-
   - 视频合集-
   - UP主-
   - 稍后再看-
   - 课程-

3. 但会 **排除**「投稿视频-」这种投稿视频目录，只处理其他类型：
   - 番剧-
   - 收藏夹-
   - 视频列表-
   - 视频合集-
   - UP主-
   - 稍后再看-
   - 课程-

4. 对于每一个被选中的任务目录 D（例如：
   /Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili/收藏夹-3743181273-ssw）
   会执行以下操作：
   - 把 D 子目录下（不限层级）的所有“非隐藏文件”移动到 D 这一层目录中；
   - 对于所有以 "." 开头的隐藏文件，**直接删除**（不会上移，也不会保留）；
   - 然后尽可能删除 D 下面的所有子目录，使目录结构尽量被“拍平”；
   - 如果移动过程中发生“文件名冲突”，会自动在新文件后面追加后缀：
       name.ext -> name__dup1.ext -> name__dup2.ext -> ...
     直到没有冲突为止（逻辑直接复用 flatten.py 里的 safe_move）。

5. 起始路径的判定规则：
   - 如果 **起始路径本身**的目录名就以上述任务前缀开头（且不是「投稿视频-」），
     则只对该目录本身做整理；
   - 否则，把起始路径当作“容器目录”，只在其 **直接子目录** 中寻找任务目录，
     并对找到的这些任务目录逐一进行拍平处理。

用法示例：

真正执行（会移动文件、删除隐藏文件与子目录）：

    python flatten_tasks.py "/Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili"

只看效果，不改动真实文件（dry-run 预览）：

    python flatten_tasks.py "/Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili" --dry-run
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from utils.constants import TASK_FOLDER_PREFIXES
from flatten import flatten_all_into  # 复用已有安全移动与重命名逻辑


EXCLUDED_PREFIX = "投稿视频-"


def is_task_root_dir(path: Path) -> bool:
    """
    判断给定目录是否是“任务根目录”（由 BiliSyncer/yutto 生成的那类）。

    规则：
    - 目录名以 TASK_FOLDER_PREFIXES 中任意前缀开头；
    - 但排除掉「投稿视频-」这种投稿视频目录。
    """
    name = path.name

    # 先排除投稿视频-
    if name.startswith(EXCLUDED_PREFIX):
        return False

    return any(name.startswith(prefix) for prefix in TASK_FOLDER_PREFIXES)


def collect_task_roots(start: Path) -> List[Path]:
    """
    根据“起始路径”收集要处理的任务根目录列表。

    1. 如果 start 本身就是任务根目录，则只返回 [start]。
    2. 否则，视作容器目录，只在其直接子目录中寻找任务根目录。
    """
    start = start.resolve()

    if not start.exists():
        raise FileNotFoundError(f"路径不存在：{start}")
    if not start.is_dir():
        raise NotADirectoryError(f"不是有效目录：{start}")

    if is_task_root_dir(start):
        return [start]

    # 否则：只在第一层子目录中查找任务根目录
    task_roots: List[Path] = []
    for child in start.iterdir():
        if not child.is_dir():
            continue
        if is_task_root_dir(child):
            task_roots.append(child.resolve())

    return task_roots


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "按 BiliSyncer 任务目录规则拍平目录："
            "自动识别任务根目录（排除“投稿视频-”），将子目录内容提升到任务根目录，并删除隐藏文件与子目录。"
        )
    )
    parser.add_argument(
        "path",
        help="起始路径：可以是某个具体任务目录，也可以是上层的 Bilibili 目录",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=8,
        help="最大并行线程数（用于移动文件），默认 8",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览将要执行的操作，不实际移动/删除任何文件或目录",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    start = Path(args.path).expanduser().resolve()

    try:
        task_roots = collect_task_roots(start)
    except (FileNotFoundError, NotADirectoryError) as e:
        logging.error(str(e))
        return

    if not task_roots:
        logging.info("在路径 %s 下未找到任何符合规则的任务目录，已退出。", start)
        return

    logging.info(
        "将在以下 %d 个任务目录上执行拍平操作%s：",
        len(task_roots),
        "（DRY-RUN 预览）" if args.dry_run else "",
    )
    for d in task_roots:
        logging.info("  - %s", d)

    jobs = max(1, int(args.jobs))

    # 线程池用于文件移动，调用现有 flatten_all_into，强制 delete_hidden=True
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for task_dir in task_roots:
            logging.info(
                "开始处理任务目录：%s%s",
                task_dir,
                "（DRY-RUN）" if args.dry_run else "",
            )
            # delete_hidden=True：删除所有以 "." 开头的隐藏文件
            # dry_run 由命令行参数控制
            flatten_all_into(
                root_dir=task_dir,
                executor=executor,
                delete_hidden=True,
                dry_run=args.dry_run,
            )

    logging.info("全部任务目录处理完成%s。", "（DRY-RUN，仅预览）" if args.dry_run else "")


if __name__ == "__main__":
    main()

