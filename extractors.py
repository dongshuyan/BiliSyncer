"""
URL提取器模块
"""

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from pathlib import Path

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
    """番剧提取器"""
    
    REGEX_MD = re.compile(r"https?://www\.bilibili\.com/bangumi/media/md(?P<media_id>\d+)")
    REGEX_EP = re.compile(r"https?://www\.bilibili\.com/bangumi/play/ep(?P<episode_id>\d+)")
    REGEX_SS = re.compile(r"https?://www\.bilibili\.com/bangumi/play/ss(?P<season_id>\d+)")
    
    def match(self, url: str) -> bool:
        """检查URL是否匹配"""
        return bool(self.REGEX_MD.match(url) or self.REGEX_EP.match(url) or self.REGEX_SS.match(url))
    
    async def extract(self, fetcher: Fetcher, url: str) -> VideoListData:
        """提取番剧列表"""
        if match_obj := self.REGEX_SS.match(url):
            season_id = SeasonId(match_obj.group("season_id"))
        elif match_obj := self.REGEX_EP.match(url):
            episode_id = EpisodeId(match_obj.group("episode_id"))
            season_id = await convert_episode_to_season(fetcher, episode_id)
        elif match_obj := self.REGEX_MD.match(url):
            media_id = MediaId(match_obj.group("media_id"))
            season_id = await convert_media_to_season(fetcher, media_id)
        else:
            raise ValueError(f"无法解析番剧URL: {url}")
        
        Logger.info(f"提取番剧: {season_id}")
        return await get_bangumi_list(fetcher, season_id)


class FavouritesExtractor(URLExtractor):
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
            try:
                video_data = await get_ugc_video_list(fetcher, avid)
                # 在使用 SESSDATA 时，如果不去事先 touch 一下视频链接的话，是无法获取 episode_data 的
                await fetcher.touch_url(avid.to_url())
                # 为收藏夹中的视频添加路径前缀
                for video in video_data["videos"]:
                    video["path"] = Path(f"收藏夹-{fav_info['title']}") / video["path"]
                videos.extend(video_data["videos"])
            except Exception as e:
                Logger.error(f"获取收藏夹视频 {avid} 失败: {e}")
                continue
        
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
            try:
                video_data = await get_ugc_video_list(fetcher, avid)
                videos.extend(video_data["videos"])
            except Exception as e:
                Logger.error(f"获取列表视频 {avid} 失败: {e}")
                continue
        
        title_prefix = "视频列表" if list_type == "series" else "视频合集"
        return {"title": f"{title_prefix}-{series_id}", "videos": videos}


class UserSpaceExtractor(URLExtractor):
    """用户空间提取器"""
    
    REGEX_SPACE = re.compile(r"https?://space\.bilibili\.com/(?P<mid>\d+)(/video)?/?$")
    
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
        
        avids = await get_user_space_videos(fetcher, mid)
        
        videos = []
        for avid in avids:
            try:
                video_data = await get_ugc_video_list(fetcher, avid)
                videos.extend(video_data["videos"])
            except Exception as e:
                Logger.error(f"获取用户视频 {avid} 失败: {e}")
                continue
        
        return {"title": f"用户-{mid}", "videos": videos}


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
            try:
                video_data = await get_ugc_video_list(fetcher, avid)
                videos.extend(video_data["videos"])
            except Exception as e:
                Logger.error(f"获取稍后再看视频 {avid} 失败: {e}")
                continue
        
        return {"title": "稍后再看", "videos": videos}


# 提取器列表（按优先级排序）
EXTRACTORS = [
    UgcVideoExtractor(),       # 投稿视频
    BangumiExtractor(),        # 番剧
    FavouritesExtractor(),     # 收藏夹
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