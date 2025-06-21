"""
批量下载器
"""

import asyncio
import subprocess
import sys
import shutil
import glob
from pathlib import Path
from typing import Optional, List, Dict

from utils.types import VideoListData, VideoInfo, DownloadOptions, AId, BvId, CId
from utils.fetcher import Fetcher
from utils.logger import Logger
from utils.csv_manager import CSVManager
from extractors import extract_video_list


class BatchDownloader:
    """批量下载器"""
    
    def __init__(self, output_dir: Path, sessdata: Optional[str] = None, extra_args: Optional[List[str]] = None, original_url: Optional[str] = None):
        """初始化批量下载器"""
        self.output_dir = output_dir
        self.sessdata = sessdata
        self.extra_args = extra_args or []
        self.original_url = original_url
        self.fetcher = Fetcher(sessdata=sessdata)
        self.csv_manager = None  # 稍后根据任务创建
    
    async def download_from_url(self, url: str) -> None:
        """从URL开始批量下载"""
        async with self.fetcher:
            try:
                # 步骤1-4: 解析URL并获取基本信息
                Logger.info("分析URL类型和获取基本信息...")
                video_list = await extract_video_list(self.fetcher, url)
                task_name = video_list["title"]
                Logger.info(f"任务名称: {task_name}")
                
                # 步骤5: 确定"带名称的输出文件夹"
                task_output_dir = self.output_dir / task_name
                task_output_dir.mkdir(parents=True, exist_ok=True)
                self.csv_manager = CSVManager(task_output_dir)
                
                Logger.info(f"任务输出目录: {task_output_dir}")
                
                # 步骤6: 检查是否存在CSV文件
                existing_csv_videos = self.csv_manager.load_video_list()
                videos_to_download = []
                
                if existing_csv_videos:
                    Logger.info("发现现有CSV文件，检查下载状态...")
                    
                    # 步骤6.1: 从CSV获取未完成的下载
                    pending_videos = self.csv_manager.get_pending_videos()
                    
                    if pending_videos:
                        # 步骤6.1.1: 有未完成的下载
                        Logger.info(f"发现 {len(pending_videos)} 个未完成的下载，继续下载任务")
                        videos_to_download = [self._csv_to_video_info(data) for data in pending_videos]
                        
                    else:
                        # 步骤6.1.2: 所有视频都已完成，检查是否有新增视频
                        Logger.info("所有视频已下载完成，检查是否有新增视频...")
                        current_videos = video_list["videos"]
                        
                        # 对比CSV中的视频和当前获取的视频
                        csv_video_urls = {video['video_url'] for video in existing_csv_videos}
                        current_video_urls = {video['avid'].to_url() for video in current_videos}
                        
                        new_video_urls = current_video_urls - csv_video_urls
                        
                        if new_video_urls:
                            Logger.info(f"发现 {len(new_video_urls)} 个新增视频，更新CSV文件")
                            # 更新CSV文件（保持现有下载状态）
                            update_url = self.original_url or url
                            self.csv_manager.update_video_list(current_videos, update_url)
                            # 只下载新增的视频
                            videos_to_download = [v for v in current_videos if v['avid'].to_url() in new_video_urls]
                        else:
                            # 步骤6.1.3: 没有新增视频，任务完成
                            Logger.info("没有发现新增视频，所有任务已完成！")
                            return
                
                else:
                    # 步骤6.2: 没有CSV文件，首次下载
                    Logger.info("首次下载，创建CSV文件...")
                    videos_to_download = video_list["videos"]
                    self.csv_manager.save_video_list(videos_to_download, self.original_url)
                
                if not videos_to_download:
                    Logger.info("没有需要下载的视频")
                    return
                
                Logger.custom(f"{task_name} ({len(videos_to_download)}个视频)", "批量下载")
                
                # 步骤7: 逐个下载
                await self._download_videos(videos_to_download, url)
                
            except Exception as e:
                Logger.error(f"批量下载失败: {e}")
                raise
    
    async def update_all_tasks(self) -> None:
        """更新所有任务：扫描输出目录下的所有任务并检查更新"""
        try:
            # 扫描所有一级子目录
            task_dirs = [d for d in self.output_dir.iterdir() if d.is_dir()]
            
            if not task_dirs:
                Logger.info("未找到任何任务目录")
                return
            
            Logger.info(f"发现 {len(task_dirs)} 个任务目录")
            
            updated_count = 0
            for task_dir in task_dirs:
                Logger.info(f"检查任务目录: {task_dir.name}")
                
                # 查找CSV文件
                csv_manager = CSVManager(task_dir)
                original_url = csv_manager.get_original_url()
                
                if original_url:
                    Logger.info(f"发现任务URL: {original_url}")
                    try:
                        # 创建临时下载器，专门用于这个任务的更新
                        task_downloader = BatchDownloader(
                            output_dir=self.output_dir,
                            sessdata=self.sessdata,
                            extra_args=self.extra_args,
                            original_url=original_url
                        )
                        
                        # 执行批量下载流程（会自动处理更新逻辑）
                        await task_downloader.download_from_url(original_url)
                        updated_count += 1
                        
                    except Exception as e:
                        Logger.error(f"更新任务失败 {task_dir.name}: {e}")
                        continue
                else:
                    Logger.warning(f"任务目录 {task_dir.name} 中未找到CSV文件或原始URL")
            
            Logger.custom(f"批量更新完成 - 成功更新 {updated_count}/{len(task_dirs)} 个任务", "批量更新")
            
        except Exception as e:
            Logger.error(f"批量更新失败: {e}")
            raise
    
    async def _download_videos(self, videos: list[VideoInfo], original_url: str) -> None:
        """步骤7: 逐个下载视频"""
        for i, video in enumerate(videos, 1):
            try:
                Logger.info(f"[{i}/{len(videos)}] 开始下载: {video['name']}")
                
                # 步骤7关键逻辑: 检查视频文件夹是否存在，如果存在就删除重新下载
                await self._cleanup_existing_video_folder(video)
                
                # 构建yutto命令
                video_url = video['avid'].to_url()
                if not self.csv_manager:
                    Logger.error("CSV管理器未初始化")
                    continue
                    
                output_dir = self.csv_manager.task_dir
                
                yutto_cmd = ["yutto", video_url, "-d", str(output_dir)]
                if self.sessdata:
                    yutto_cmd.extend(["-c", self.sessdata])
                yutto_cmd.extend(self.extra_args)
                
                # 调用之前的单视频下载方法
                await self._download_single_video(video, output_dir)
                
                # 更新CSV文件中的下载状态
                if self.csv_manager:
                    self.csv_manager.mark_video_downloaded(video_url)
                    
                Logger.info(f"[{i}/{len(videos)}] 下载成功: {video['name']}")
                    
            except Exception as e:
                Logger.error(f"下载视频 {video['name']} 失败: {e}")
                continue
        
        # 显示最终统计
        if self.csv_manager:
            stats = self.csv_manager.get_download_stats()
            Logger.custom(f"下载完成 - 成功: {stats['downloaded']}, 总计: {stats['total']}", "批量下载")
    
    async def _cleanup_existing_video_folder(self, video: VideoInfo) -> None:
        """清理已存在的视频文件夹和文件"""
        if not self.csv_manager:
            return
            
        # yutto下载时可能创建以视频标题命名的文件夹或直接创建文件
        video_name = self._sanitize_filename(video['title'])
        task_dir = self.csv_manager.task_dir
        
        cleaned_items = []
        
        # 1. 检查并删除文件夹
        video_folder_path = task_dir / video_name
        if video_folder_path.exists() and video_folder_path.is_dir():
            try:
                shutil.rmtree(video_folder_path, onerror=self._remove_readonly)
                cleaned_items.append(f"文件夹: {video_name}")
            except Exception as e:
                Logger.warning(f"删除文件夹时出现警告: {video_folder_path} - {e}")
        
        # 2. 检查并删除可能的视频文件和相关文件
        # yutto可能创建的文件扩展名
        possible_extensions = ['.mp4', '.flv', '.ass', '.srt', '_audio.m4s', '_video.m4s', '-poster.jpg']
        
        for ext in possible_extensions:
            video_file_path = task_dir / f"{video_name}{ext}"
            if video_file_path.exists():
                try:
                    video_file_path.unlink()
                    cleaned_items.append(f"文件: {video_name}{ext}")
                except Exception as e:
                    Logger.warning(f"删除文件时出现警告: {video_file_path} - {e}")
        
        # 3. 检查中文字幕文件（可能包含特殊字符）
        for item in task_dir.iterdir():
            if item.name.startswith(video_name) and ('中文' in item.name or '自动生成' in item.name):
                try:
                    item.unlink()
                    cleaned_items.append(f"字幕文件: {item.name}")
                except Exception as e:
                    Logger.warning(f"删除字幕文件时出现警告: {item} - {e}")
        
        if cleaned_items:
            Logger.info(f"清理已存在的视频相关内容: {video_name}")
            for item in cleaned_items:
                Logger.debug(f"  已删除 {item}")
        else:
            Logger.debug(f"未发现需要清理的内容: {video_name}")
    
    def _remove_readonly(self, func, path, exc):
        """处理只读文件删除"""
        import stat
        import os
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass  # 忽略系统文件删除错误
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # 移除或替换文件名中的非法字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
    
    async def _download_single_video(self, video: VideoInfo, output_dir: Path) -> None:
        """调用原版yutto下载单个视频"""
        
        # 构建yutto命令
        yutto_cmd = ["yutto"]
        
        # 视频URL
        video_url = str(video['avid'].to_url())
        yutto_cmd.append(video_url)
        
        # 输出目录 - 使用视频标题创建子目录
        video_output_dir = output_dir / self._sanitize_filename(video['title'])
        yutto_cmd.extend(["-d", str(video_output_dir)])
        
        # 如果有SESSDATA，添加-c参数
        if self.sessdata:
            yutto_cmd.extend(["-c", self.sessdata])
        
        # 添加用户额外参数
        yutto_cmd.extend(self.extra_args)
        
        try:
            Logger.debug(f"执行命令: {' '.join(yutto_cmd)}")
            
            # 执行yutto命令，捕获输出并实时转发到Logger
            process = await asyncio.create_subprocess_exec(
                *yutto_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=Path(__file__).parent
            )
            
            # 实时读取和转发输出
            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    
                    # 解码输出并发送到Logger
                    output = line.decode('utf-8', errors='ignore').strip()
                    if output:
                        # 根据输出内容判断日志级别
                        if 'error' in output.lower() or 'failed' in output.lower():
                            Logger.error(f"[yutto] {output}")
                        elif 'warning' in output.lower() or 'warn' in output.lower():
                            Logger.warning(f"[yutto] {output}")
                        elif 'downloading' in output.lower() or 'progress' in output.lower() or '%' in output:
                            Logger.custom(output, "下载进度")
                        else:
                            Logger.info(f"[yutto] {output}")
            
            # 等待进程完成
            return_code = await process.wait()
            
            if return_code != 0:
                raise Exception(f"yutto下载失败，返回码: {return_code}")
                
        except Exception as e:
            Logger.error(f"调用yutto失败: {e}")
            raise
    
    def _csv_to_video_info(self, csv_data: Dict[str, str]) -> VideoInfo:
        """将CSV数据转换为VideoInfo"""
        # 根据avid类型创建对应的AvId对象
        avid_str = csv_data['avid']
        if avid_str.startswith('BV') or avid_str.startswith('bv'):
            avid = BvId(avid_str)
        else:
            avid = AId(avid_str)
        
        # 处理pubdate字段 - 可能是Unix时间戳或可读格式
        pubdate_str = csv_data.get('pubdate', '0')
        if pubdate_str == '未知' or not pubdate_str:
            pubdate = 0
        elif pubdate_str.isdigit():
            # 如果是纯数字，说明是Unix时间戳
            pubdate = int(pubdate_str)
        else:
            # 如果是日期字符串，尝试解析为Unix时间戳
            try:
                from datetime import datetime
                dt = datetime.strptime(pubdate_str, '%Y-%m-%d %H:%M:%S')
                pubdate = int(dt.timestamp())
            except ValueError:
                Logger.warning(f"无法解析pubdate: {pubdate_str}")
                pubdate = 0
        
        return {
            'id': 1,  # 默认id
            'name': csv_data['name'],
            'title': csv_data['title'],
            'avid': avid,
            'cid': CId(csv_data['cid']),
            'path': Path(csv_data['download_path']),
            'pubdate': pubdate
        } 