#!/usr/bin/env python3
"""
Yutto-Batch: 精简版B站批量下载工具
"""

import sys
import asyncio
from typing import Optional
from pathlib import Path

from batch_downloader import BatchDownloader
from utils.logger import Logger
from utils.config_manager import ConfigManager


def print_help():
    """打印帮助信息"""
    help_text = """
Yutto-Batch - 精简版B站批量下载工具

用法:
    python main.py <url> [选项]
    python main.py --update [选项]

支持的URL类型:
    - 投稿视频: https://www.bilibili.com/video/BV1xx411c7mD
    - 番剧: https://www.bilibili.com/bangumi/play/ss12345
    - 课程: https://www.bilibili.com/cheese/play/ss12345
    - 收藏夹: https://space.bilibili.com/123456/favlist?fid=789012
    - 视频列表: https://space.bilibili.com/123456/lists/789012?type=series
    - 视频合集: https://space.bilibili.com/123456/lists/789012?type=season
    - 个人空间: https://space.bilibili.com/123456
    - 稍后再看: https://www.bilibili.com/watchlater

选项:
    -h, --help          显示此帮助信息
    -o, --output DIR    指定下载目录 (默认: ~/Downloads)
    -c, --cookie STR    设置SESSDATA cookie
    --config NAME       使用指定的配置文件 (不含.yaml扩展名)
    --update            更新模式：扫描输出目录下所有任务并检查更新
    --vip-strict        启用严格VIP模式（传递给yutto）
    
示例:
    python main.py "https://www.bilibili.com/video/BV1xx411c7mD"
    python main.py "https://space.bilibili.com/123456/favlist?fid=789012" -o ./my_downloads
    python main.py --update -c "cookie" -o "/path/to/downloads"
    python main.py "https://www.bilibili.com/video/BV1xx411c7mD" --vip-strict
    python main.py "https://www.bilibili.com/video/BV1xx411c7mD" --config vip
"""
    print(help_text)


def parse_args():
    """解析命令行参数"""
    args = sys.argv[1:]
    
    if not args or '-h' in args or '--help' in args:
        print_help()
        sys.exit(0)
    
    # 检查是否使用配置文件
    config_name = None
    config_manager = ConfigManager()
    
    # 先检查是否有--config参数
    if '--config' in args:
        config_index = args.index('--config')
        if config_index + 1 < len(args):
            config_name = args[config_index + 1]
            # 移除--config参数
            args = args[:config_index] + args[config_index + 2:]
    
    # 加载配置文件
    config_data = {}
    if config_name:
        config_data = config_manager.get_config_for_download(config_name) or {}
        if not config_data:
            Logger.error(f"无法加载配置文件: {config_name}")
            sys.exit(1)
        Logger.info(f"使用配置文件: {config_name}")
    
    # 检查是否是更新模式
    update_mode = '--update' in args
    
    if update_mode:
        # 更新模式
        url = None
        output_dir = Path(config_data.get('output_dir', '~/Downloads')).expanduser()
        sessdata = config_data.get('sessdata', None)
        extra_args = config_data.get('extra_args', []).copy()
        
        # 添加配置文件中的选项
        if config_data.get('vip_strict', False):
            extra_args.append('--vip-strict')
        if config_data.get('debug', False):
            extra_args.append('--debug')
        
        i = 0
        while i < len(args):
            if args[i] == '--update':
                i += 1
            elif args[i] in ['-o', '--output'] and i + 1 < len(args):
                output_dir = Path(args[i + 1]).expanduser()
                i += 2
            elif args[i] in ['-c', '--cookie'] and i + 1 < len(args):
                sessdata = args[i + 1]
                i += 2
            elif args[i] == '--vip-strict':
                # 将vip-strict参数传递给yutto
                extra_args.append('--vip-strict')
                i += 1
            else:
                # 未识别的参数传递给yutto
                extra_args.append(args[i])
                i += 1
    else:
        # 普通下载模式
        url = args[0]
        output_dir = Path(config_data.get('output_dir', './downloads'))
        sessdata = config_data.get('sessdata', None)
        extra_args = config_data.get('extra_args', []).copy()
        
        # 添加配置文件中的选项
        if config_data.get('vip_strict', False):
            extra_args.append('--vip-strict')
        if config_data.get('debug', False):
            extra_args.append('--debug')
        
        i = 1
        while i < len(args):
            if args[i] in ['-o', '--output'] and i + 1 < len(args):
                output_dir = Path(args[i + 1])
                i += 2
            elif args[i] in ['-c', '--cookie'] and i + 1 < len(args):
                sessdata = args[i + 1]
                i += 2
            elif args[i] == '--vip-strict':
                # 将vip-strict参数传递给yutto
                extra_args.append('--vip-strict')
                i += 1
            else:
                # 未识别的参数传递给yutto
                extra_args.append(args[i])
                i += 1
    
    return url, output_dir, sessdata, extra_args, update_mode


async def main():
    """主函数"""
    try:
        url, output_dir, sessdata, extra_args, update_mode = parse_args()
        
        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建批量下载器
        downloader = BatchDownloader(
            output_dir=output_dir,
            sessdata=sessdata,
            extra_args=extra_args,
            original_url=url
        )
        
        if update_mode:
            # 更新模式
            Logger.info("=== 批量更新模式 ===")
            Logger.info(f"扫描目录: {output_dir}")
            if extra_args:
                Logger.info(f"额外参数传递给yutto: {' '.join(extra_args)}")
            
            await downloader.update_all_tasks()
            
        else:
            # 普通下载模式
            if url is None:
                Logger.error("普通下载模式需要提供URL")
                sys.exit(1)
                
            Logger.info(f"URL: {url}")
            Logger.info(f"输出目录: {output_dir}")
            if extra_args:
                Logger.info(f"额外参数传递给yutto: {' '.join(extra_args)}")
            
            # 开始批量下载
            await downloader.download_from_url(url)
        
        Logger.info("任务完成！")
        
    except KeyboardInterrupt:
        Logger.info("用户中断操作")
        sys.exit(1)
    except Exception as e:
        Logger.error(f"操作失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 