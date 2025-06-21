"""
类型定义
"""

from typing import TypedDict, NamedTuple, Union
from pathlib import Path


class BilibiliId(NamedTuple):
    """所有 bilibili id 的基类"""
    value: str

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.__str__()

    def to_dict(self) -> dict[str, str]:
        raise NotImplementedError("请不要直接使用 BilibiliId")


class AvId(BilibiliId):
    """AvId基类"""
    
    def to_dict(self) -> dict[str, str]:
        raise NotImplementedError("请不要直接使用 AvId")

    def to_url(self) -> str:
        raise NotImplementedError("请不要直接使用 AvId")


class AId(AvId):
    """AID"""

    def to_dict(self):
        return {"aid": self.value, "bvid": ""}

    def to_url(self) -> str:
        return f"https://www.bilibili.com/video/av{self.value}"


class BvId(AvId):
    """BVID"""

    def to_dict(self):
        return {"aid": "", "bvid": self.value}

    def to_url(self) -> str:
        return f"https://www.bilibili.com/video/{self.value}"


class CId(BilibiliId):
    """视频 ID"""

    def to_dict(self):
        return {"cid": self.value}


class EpisodeId(BilibiliId):
    """番剧剧集 ID"""

    def to_dict(self):
        return {"episode_id": self.value}


class MediaId(BilibiliId):
    """番剧 ID"""

    def to_dict(self):
        return {"media_id": self.value}


class SeasonId(BilibiliId):
    """番剧（季） ID"""

    def to_dict(self):
        return {"season_id": self.value}


class MId(BilibiliId):
    """用户 ID"""

    def to_dict(self):
        return {"mid": self.value}


class FId(BilibiliId):
    """收藏夹 ID"""

    def to_dict(self):
        return {"fid": self.value}


class SeriesId(BilibiliId):
    """视频合集 ID"""

    def to_dict(self):
        return {"series_id": self.value}


class VideoInfo(TypedDict):
    """视频信息"""
    id: int
    name: str
    avid: AvId
    cid: CId
    title: str
    path: Path
    pubdate: int  # 发布时间（Unix时间戳）


class VideoListData(TypedDict):
    """视频列表数据"""
    title: str
    videos: list[VideoInfo]


class DownloadOptions(TypedDict):
    """下载选项"""
    output_dir: Path
    sessdata: str | None 