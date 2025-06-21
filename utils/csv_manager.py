"""
CSV文件管理模块
用于保存和管理视频下载状态
"""

import csv
import glob
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from utils.types import VideoInfo
from utils.logger import Logger


class CSVManager:
    """CSV文件管理器"""
    
    def __init__(self, task_dir: Path):
        """
        初始化CSV管理器
        task_dir: 当前任务的目录（比如"收藏夹-声音"文件夹）
        """
        self.task_dir = task_dir
        self.task_dir.mkdir(parents=True, exist_ok=True)
    
    def _detect_csv_encoding(self, file_path: Path) -> str:
        """智能检测CSV文件编码"""
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    # 尝试读取前几行
                    f.readline()
                    return encoding
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        
        # 如果都失败了，默认使用utf-8
        Logger.warning(f"无法检测CSV文件编码，使用默认utf-8: {file_path}")
        return 'utf-8'
    
    def _generate_csv_filename(self) -> str:
        """生成基于当前时间的CSV文件名"""
        now = datetime.now()
        return f"{now.strftime('%y-%m-%d-%H-%M')}.csv"
    
    def _find_latest_csv(self) -> Optional[Path]:
        """查找任务目录下最新的CSV文件"""
        pattern = str(self.task_dir / "??-??-??-??-??.csv")
        csv_files = glob.glob(pattern)
        
        if not csv_files:
            Logger.info(f"未找到现有的CSV文件：{self.task_dir}")
            return None
        
        # 按文件名排序，最新的在最后
        csv_files.sort()
        latest_file = Path(csv_files[-1])
        Logger.info(f"找到现有CSV文件：{latest_file.name}")
        return latest_file
    
    def save_video_list(self, videos: List[VideoInfo], original_url: Optional[str] = None) -> Path:
        """保存视频列表到CSV文件（仅用于新任务）"""
        csv_filename = self._generate_csv_filename()
        csv_path = self.task_dir / csv_filename
        temp_path = self.task_dir / f"temp_{csv_filename}"
        
        try:
            # 先写入临时文件，使用UTF-8-BOM编码确保Excel正确识别
            with open(temp_path, 'w', newline='', encoding='utf-8-sig') as f:
                # 第一行写入原始URL（如果提供）
                if original_url:
                    f.write(f"# Original URL: {original_url}\n")
                
                writer = csv.DictWriter(f, fieldnames=[
                    'video_url', 'title', 'name', 'download_path', 
                    'downloaded', 'avid', 'cid', 'pubdate'
                ])
                writer.writeheader()
                
                for video in videos:
                    # 将Unix时间戳转换为可读格式
                    pubdate_unix = video.get('pubdate', 0)
                    if pubdate_unix:
                        pubdate_str = datetime.fromtimestamp(pubdate_unix).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        pubdate_str = "未知"
                    
                    writer.writerow({
                        'video_url': video['avid'].to_url(),
                        'title': video['title'],
                        'name': video['name'],
                        'download_path': str(video['path']),
                        'downloaded': False,
                        'avid': str(video['avid']),
                        'cid': str(video['cid']),
                        'pubdate': pubdate_str
                    })
            
            # 验证临时文件写入成功后，移动到正式位置
            shutil.move(str(temp_path), str(csv_path))
            Logger.info(f"已保存视频列表到: {csv_path}")
            return csv_path
            
        except Exception as e:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()
            Logger.error(f"保存CSV文件失败: {e}")
            raise
    
    def update_video_list(self, new_videos: List[VideoInfo], original_url: str) -> Path:
        """更新现有的视频列表，合并新视频并保持已下载状态"""
        current_csv = self._find_latest_csv()
        
        if current_csv is None:
            # 如果没有现有CSV，直接创建新的
            return self.save_video_list(new_videos, original_url)
        
        try:
            # 读取现有数据
            existing_videos = self.load_video_list()
            if existing_videos is None:
                existing_videos = []
            
            # 创建现有视频的URL映射（保留下载状态）
            existing_video_map = {video['video_url']: video for video in existing_videos}
            
            # 生成新的CSV文件名（带时间戳）
            new_csv_filename = self._generate_csv_filename()
            new_csv_path = self.task_dir / new_csv_filename
            temp_path = self.task_dir / f"temp_{new_csv_filename}"
            
            # 合并视频列表
            merged_videos = []
            
            # 处理新视频列表
            for video in new_videos:
                video_url = video['avid'].to_url()
                
                if video_url in existing_video_map:
                    # 已存在的视频，保持原有下载状态
                    existing_data = existing_video_map[video_url]
                    merged_videos.append(existing_data)
                else:
                    # 新增的视频，设置为未下载
                    pubdate_unix = video.get('pubdate', 0)
                    if pubdate_unix:
                        pubdate_str = datetime.fromtimestamp(pubdate_unix).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        pubdate_str = "未知"
                    
                    merged_videos.append({
                        'video_url': video_url,
                        'title': video['title'],
                        'name': video['name'],
                        'download_path': str(video['path']),
                        'downloaded': 'False',
                        'avid': str(video['avid']),
                        'cid': str(video['cid']),
                        'pubdate': pubdate_str
                    })
            
            # 安全写入新的CSV文件
            with open(temp_path, 'w', newline='', encoding='utf-8-sig') as f:
                # 写入原始URL
                f.write(f"# Original URL: {original_url}\n")
                
                if merged_videos:
                    writer = csv.DictWriter(f, fieldnames=merged_videos[0].keys())
                    writer.writeheader()
                    writer.writerows(merged_videos)
            
            # 验证写入成功后，替换原文件
            shutil.move(str(temp_path), str(new_csv_path))
            
            # 删除旧的CSV文件
            if current_csv != new_csv_path:
                current_csv.unlink()
                Logger.debug(f"已删除旧CSV文件: {current_csv.name}")
            
            Logger.info(f"已更新视频列表到: {new_csv_path}")
            return new_csv_path
            
        except Exception as e:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()
            Logger.error(f"更新CSV文件失败: {e}")
            raise
    
    def load_video_list(self) -> Optional[List[Dict[str, str]]]:
        """从CSV文件加载视频列表"""
        csv_path = self._find_latest_csv()
        
        if csv_path is None:
            return None
        
        try:
            # 智能检测文件编码
            encoding = self._detect_csv_encoding(csv_path)
            
            videos = []
            with open(csv_path, 'r', encoding=encoding) as f:
                # 跳过第一行的原始URL（如果存在）
                first_line = f.readline()
                if not first_line.startswith("# Original URL:"):
                    # 如果第一行不是URL，重新回到文件开头
                    f.seek(0)
                
                reader = csv.DictReader(f)
                for row in reader:
                    videos.append(row)
            
            Logger.info(f"从CSV文件加载了 {len(videos)} 个视频记录")
            return videos
            
        except Exception as e:
            Logger.error(f"读取CSV文件失败: {e}")
            return None
    
    def get_pending_videos(self) -> Optional[List[Dict[str, str]]]:
        """获取未下载的视频列表"""
        videos = self.load_video_list()
        if videos is None:
            return None
        
        pending_videos = [v for v in videos if v['downloaded'].lower() != 'true']
        
        if pending_videos:
            Logger.info(f"发现 {len(pending_videos)} 个未下载的视频")
        else:
            Logger.info("所有视频已下载完成")
        
        return pending_videos
    
    def mark_video_downloaded(self, video_url: str) -> None:
        """标记视频为已下载并更新CSV文件"""
        current_csv = self._find_latest_csv()
        
        if current_csv is None:
            Logger.warning("未找到CSV文件，无法标记下载状态")
            return
        
        try:
            # 智能检测文件编码
            encoding = self._detect_csv_encoding(current_csv)
            
            # 读取现有数据
            videos = []
            url_line = None
            with open(current_csv, 'r', encoding=encoding) as f:
                # 检查第一行是否为原始URL
                first_line = f.readline()
                if first_line.startswith("# Original URL:"):
                    url_line = first_line
                else:
                    # 如果第一行不是URL，重新回到文件开头
                    f.seek(0)
                
                reader = csv.DictReader(f)
                for row in reader:
                    if row['video_url'] == video_url:
                        row['downloaded'] = 'True'
                    videos.append(row)
            
            # 生成新的CSV文件名
            new_csv_filename = self._generate_csv_filename()
            new_csv_path = self.task_dir / new_csv_filename
            temp_path = self.task_dir / f"temp_{new_csv_filename}"
            
            # 先写入临时文件，使用UTF-8-BOM编码确保Excel正确识别
            with open(temp_path, 'w', newline='', encoding='utf-8-sig') as f:
                # 写入原始URL行（如果存在）
                if url_line:
                    f.write(url_line)
                
                if videos:
                    writer = csv.DictWriter(f, fieldnames=videos[0].keys())
                    writer.writeheader()
                    writer.writerows(videos)
            
            # 验证写入成功后，替换文件
            shutil.move(str(temp_path), str(new_csv_path))
            
            # 删除旧的CSV文件
            if current_csv != new_csv_path:
                current_csv.unlink()
                Logger.debug(f"已删除旧CSV文件: {current_csv.name}")
            
            Logger.debug(f"已更新CSV文件并标记下载: {video_url}")
            
        except Exception as e:
            # 清理临时文件
            temp_path = self.task_dir / f"temp_{self._generate_csv_filename()}"
            if temp_path.exists():
                temp_path.unlink()
            Logger.error(f"更新CSV文件失败: {e}")
    
    def get_download_stats(self) -> Dict[str, int]:
        """获取下载统计信息"""
        videos = self.load_video_list()
        if not videos:
            return {'total': 0, 'downloaded': 0, 'pending': 0}
        
        total = len(videos)
        downloaded = sum(1 for v in videos if v['downloaded'].lower() == 'true')
        pending = total - downloaded
        
        return {
            'total': total,
            'downloaded': downloaded, 
            'pending': pending
        }
    
    def get_original_url(self) -> Optional[str]:
        """从CSV文件中获取原始URL"""
        csv_path = self._find_latest_csv()
        
        if csv_path is None:
            return None
        
        try:
            # 智能检测文件编码
            encoding = self._detect_csv_encoding(csv_path)
            
            with open(csv_path, 'r', encoding=encoding) as f:
                first_line = f.readline().strip()
                if first_line.startswith("# Original URL:"):
                    return first_line[15:].strip()  # 去掉"# Original URL:"前缀
            return None
            
        except Exception as e:
            Logger.error(f"读取原始URL失败: {e}")
            return None 