"""
视频提取器模块
用于从不同类型的B站URL中提取视频信息
"""

import re
import asyncio
from pathlib import Path
from typing import Dict, List, Any
from utils.logger import Logger
from utils.fetcher import Fetcher
from api.bilibili import (
    get_favourite_avids, get_favourite_info, get_user_space_videos,
    get_series_videos, get_watch_later_avids, get_bangumi_list,
    get_season_id_by_media_id, get_season_id_by_episode_id, get_user_name,
    get_ugc_video_list, get_bangumi_episode_list, get_bangumi_episode_info
)
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from utils.types import *
from utils.fetcher import Fetcher
from utils.logger import Logger
from api.bilibili import *


class URLExtractor(ABC):
    """URL提取器基类"""
    
    @abstractmethod
    def match(self, url: str) -> bool:
        """检查URL是否匹配此提取器"""
        pass
    
    @abstractmethod
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取视频列表"""
        pass
    
    def resolve_shortcut(self, url: str) -> Tuple[bool, str]:
        """解析快捷方式"""
        return False, url


class UgcVideoExtractor(URLExtractor):
    """投稿视频提取器"""
    
    REGEX_AV = re.compile(r"https?://www\.bilibili\.com/video/av(?P<aid>\d+)/?")
    REGEX_BV = re.compile(r"https?://www\.bilibili\.com/video/(?P<bvid>(bv|BV)\w+)/?")
    REGEX_AV_ID = re.compile(r"av(?P<aid>\d+)")
    REGEX_BV_ID = re.compile(r"(?P<bvid>(bv|BV)\w+)")
    
    def resolve_shortcut(self, url: str) -> Tuple[bool, str]:
        """解析快捷方式"""
        if match_obj := self.REGEX_AV_ID.match(url):
            return True, f"https://www.bilibili.com/video/av{match_obj.group('aid')}"
        elif match_obj := self.REGEX_BV_ID.match(url):
            return True, f"https://www.bilibili.com/video/{match_obj.group('bvid')}"
        return False, url
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_AV.match(url) or self.REGEX_BV.match(url))
    
    def _extract_avid(self, url: str) -> AvId:
        """从URL提取AVID"""
        if match_obj := self.REGEX_AV.match(url):
            return AId(match_obj.group("aid"))
        elif match_obj := self.REGEX_BV.match(url):
            return BvId(match_obj.group("bvid"))
        raise ValueError(f"无法从URL提取AVID: {url}")
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取投稿视频列表"""
        avid = self._extract_avid(url)
        Logger.info(f"提取投稿视频: {avid}")
        return await get_ugc_video_list(fetcher, avid)


class BangumiExtractor(URLExtractor):
    """番剧提取器（批量下载所有集数）"""
    
    REGEX_MD = re.compile(r"https?://www\.bilibili\.com/bangumi/media/md(?P<media_id>\d+)")
    REGEX_EP = re.compile(r"https?://www\.bilibili\.com/bangumi/play/ep(?P<episode_id>\d+)")
    REGEX_SS = re.compile(r"https?://www\.bilibili\.com/bangumi/play/ss(?P<season_id>\d+)")
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_MD.match(url) or self.REGEX_EP.match(url) or self.REGEX_SS.match(url))
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取番剧视频列表"""
        # 解析不同类型的URL获取season_id
        season_id = await self._parse_season_id(fetcher, url)
        Logger.info(f"提取番剧: {season_id}")
        
        # 获取番剧标题和剧集ID列表（仅获取ID，不获取详细信息）
        bangumi_title, episode_ids = await get_bangumi_episode_list(fetcher, season_id)
        
        videos = []
        for i, episode_id in enumerate(episode_ids):
            # 创建占位符视频条目，下载时再获取详细信息
            video = {
                "avid": BvId("BV1"),  # 占位符，下载时再获取
                "cid": CId("0"),  # 占位符，下载时再获取
                "title": "",  # 空标题，下载时再获取
                "name": "",   # 空名称，下载时再获取
                "pubdate": 0, # 番剧没有pubdate概念
                "author": "", # 空作者，下载时再获取
                "duration": 0, # 空时长，下载时再获取
                "path": Path(f"{bangumi_title}/第{i+1}话"),  # 临时路径，下载时会更新
                "status": "pending",  # 标记为待处理，需要下载时再获取详细信息
                "episode_id": episode_id  # 保存episode_id用于后续获取详细信息
            }
            videos.append(video)
        
        return {"title": bangumi_title, "videos": videos}
    
    async def _parse_season_id(self, fetcher: Fetcher, url: str) -> str:
        """根据URL类型获取season_id"""
        if match_obj := self.REGEX_MD.match(url):
            media_id = match_obj.group("media_id")
            return await get_season_id_by_media_id(fetcher, media_id)
        elif match_obj := self.REGEX_EP.match(url):
            episode_id = match_obj.group("episode_id")
            return await get_season_id_by_episode_id(fetcher, episode_id)
        elif match_obj := self.REGEX_SS.match(url):
            return match_obj.group("season_id")
        else:
            raise ValueError(f"无法解析番剧URL: {url}")


class FavouriteExtractor(URLExtractor):
    """收藏夹提取器"""
    
    REGEX_FAV = re.compile(r"https?://space\.bilibili\.com/(?P<mid>\d+)/favlist\?fid=(?P<fid>\d+)((&ftype=create)|$)")
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_FAV.match(url))
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取收藏夹视频列表"""
        match_obj = self.REGEX_FAV.match(url)
        if not match_obj:
            raise ValueError(f"无法解析收藏夹URL: {url}")
        
        fid = FId(match_obj.group("fid"))
        Logger.info(f"提取收藏夹: {fid}")
        
        fav_info = await get_favourite_info(fetcher, fid)
        avids = await get_favourite_avids(fetcher, fid)
        
        videos = []
        for avid in avids:
            # 创建占位符视频条目，稍后按需获取详细信息
            video = {
                "avid": avid,
                "cid": CId("0"),  # 占位符
                "title": "",  # 空标题，稍后获取
                "name": "",   # 空名称，稍后获取
                "pubdate": 0, # 空发布时间，稍后获取
                "author": "", # 空作者，稍后获取
                "duration": 0, # 空时长，稍后获取
                "path": Path(f"收藏夹-{fav_info['title']}/{avid}"),
                "status": "pending"  # 标记为待处理，需要下载时再获取详细信息
            }
            videos.append(video)
        
        return {"title": f"收藏夹-{fav_info['title']}", "videos": videos}


class SeriesExtractor(URLExtractor):
    """视频列表/合集提取器"""
    
    REGEX_SERIES = re.compile(r"https?://space\.bilibili\.com/(?P<mid>\d+)/lists/(?P<series_id>\d+)\?type=(?P<type>series|season)")
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_SERIES.match(url))
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取视频列表"""
        match_obj = self.REGEX_SERIES.match(url)
        if not match_obj:
            raise ValueError(f"无法解析视频列表URL: {url}")
        
        mid = MId(match_obj.group("mid"))
        series_id = SeriesId(match_obj.group("series_id"))
        list_type = match_obj.group("type")
        
        Logger.info(f"提取{'视频列表' if list_type == 'series' else '视频合集'}: {series_id}")
        
        avids = await get_series_videos(fetcher, series_id, mid)
        
        videos = []
        for avid in avids:
            # 创建占位符视频条目，稍后按需获取详细信息
            video = {
                "avid": avid,
                "cid": CId("0"),  # 占位符
                "title": "",  # 空标题，稍后获取
                "name": "",   # 空名称，稍后获取
                "pubdate": 0, # 空发布时间，稍后获取
                "author": "", # 空作者，稍后获取
                "duration": 0, # 空时长，稍后获取
                "path": Path(f"{'视频列表' if list_type == 'series' else '视频合集'}-{series_id}/{avid}"),
                "status": "pending"  # 标记为待处理，需要下载时再获取详细信息
            }
            videos.append(video)
        
        title_prefix = "视频列表" if list_type == "series" else "视频合集"
        return {"title": f"{title_prefix}-{series_id}", "videos": videos}


class UserSpaceExtractor(URLExtractor):
    """用户空间提取器"""
    
    REGEX_SPACE = re.compile(r"https?://space\.bilibili\.com/(?P<mid>\d+)(/video)?/?(?:\?.*)?")
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_SPACE.match(url))
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取用户空间视频"""
        match_obj = self.REGEX_SPACE.match(url)
        if not match_obj:
            raise ValueError(f"无法解析用户空间URL: {url}")
        
        mid = MId(match_obj.group("mid"))
        Logger.info(f"提取用户空间: {mid}")
        
        # 获取用户名和视频列表（仅ID）
        username = await get_user_name(fetcher, mid)
        avids = await get_user_space_videos(fetcher, mid)
        
        videos = []
        for avid in avids:
            # 创建占位符视频条目，稍后按需获取详细信息
            video = {
                "avid": avid,
                "cid": CId("0"),  # 占位符，下载时再获取
                "title": "",  # 空标题，稍后获取
                "name": "",   # 空名称，稍后获取
                "pubdate": 0, # 空发布时间，稍后获取
                "author": username, # 使用获取到的用户名
                "duration": 0, # 空时长，稍后获取
                "path": Path(f"用户-{mid}-{username}/{avid}"),
                "status": "pending"  # 标记为待处理，需要下载时再获取详细信息
            }
            videos.append(video)
        
        return {"title": f"用户-{mid}-{username}", "videos": videos}


class WatchLaterExtractor(URLExtractor):
    """稍后再看提取器"""
    
    REGEX_WATCH_LATER = re.compile(r"https?://www\.bilibili\.com/(watchlater|list/watchlater)")
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_WATCH_LATER.match(url))
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取稍后再看列表"""
        Logger.info("提取稍后再看列表")
        
        avids = await get_watch_later_avids(fetcher)
        
        videos = []
        for avid in avids:
            # 创建占位符视频条目，稍后按需获取详细信息
            video = {
                "avid": avid,
                "cid": CId("0"),  # 占位符
                "title": "",  # 空标题，稍后获取
                "name": "",   # 空名称，稍后获取
                "pubdate": 0, # 空发布时间，稍后获取
                "author": "", # 空作者，稍后获取
                "duration": 0, # 空时长，稍后获取
                "path": Path(f"稍后再看/{avid}"),
                "status": "pending"  # 标记为待处理，需要下载时再获取详细信息
            }
            videos.append(video)
        
        return {"title": "稍后再看", "videos": videos}


# 提取器列表（按优先级排序）
EXTRACTORS = [
    UgcVideoExtractor(),       # 投稿视频
    BangumiExtractor(),        # 番剧
    FavouriteExtractor(),     # 收藏夹
    SeriesExtractor(),         # 视频列表/合集
    WatchLaterExtractor(),     # 稍后再看
    UserSpaceExtractor(),      # 用户空间（放在最后，因为正则最宽泛）
]


async def extract_video_list(fetcher: Fetcher, url: str) -> VideoListData:
    """从URL提取视频列表"""
    # 首先尝试解析快捷方式
    original_url = url
    for extractor in EXTRACTORS:
        matched, resolved_url = extractor.resolve_shortcut(url)
        if matched:
            url = resolved_url
            Logger.info(f"快捷方式解析: {original_url} -> {url}")
            break
    
    # 获取重定向后的URL
    url = await fetcher.get_redirected_url(url)
    if url != original_url:
        Logger.info(f"URL重定向: {original_url} -> {url}")
    
    # 匹配提取器
    for extractor in EXTRACTORS:
        if extractor.match(url):
            Logger.info(f"使用提取器: {extractor.__class__.__name__}")
            return await extractor.extract(fetcher, url)
    
    raise ValueError(f"不支持的URL类型: {url}") 