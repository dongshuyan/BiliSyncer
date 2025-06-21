"""
B站API接口
"""

import re
from typing import Any, Dict, List, Optional, cast
from utils.types import *
from utils.fetcher import Fetcher
from utils.logger import Logger


# 移除format_avid_dict函数，直接使用avid.to_dict()


async def get_ugc_video_info(fetcher: Fetcher, avid: AvId) -> Dict[str, Any]:
    """获取投稿视频信息"""
    info_api = "https://api.bilibili.com/x/web-interface/view?aid={aid}&bvid={bvid}"
    
    res_json = await fetcher.fetch_json(info_api.format(**avid.to_dict()))
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取视频 {avid} 信息: {res_json.get('message') if res_json else 'Unknown error'}")
    
    return res_json["data"]


async def get_ugc_video_list(fetcher: Fetcher, avid: AvId) -> VideoListData:
    """获取投稿视频分P列表"""
    video_info = await get_ugc_video_info(fetcher, avid)
    video_title = video_info["title"]
    video_pubdate = video_info.get("pubdate", 0)  # 获取发布时间，默认为0
    
    # 获取分P列表
    list_api = "https://api.bilibili.com/x/player/pagelist?aid={aid}&bvid={bvid}&jsonp=jsonp"
    res_json = await fetcher.fetch_json(list_api.format(**avid.to_dict()))
    
    if not res_json or not res_json.get("data"):
        Logger.warning(f"视频 {avid} 分P信息获取失败")
        return {"title": video_title, "videos": []}
    
    videos = []
    for i, item in enumerate(cast(List[Any], res_json["data"])):
        part_name = item["part"]
        if not part_name or part_name in ["", "未命名"]:
            part_name = f"{video_title}_P{i + 1:02}"
        
        videos.append({
            "id": i + 1,
            "name": part_name,
            "avid": BvId(video_info["bvid"]) if video_info.get("bvid") else AId(str(video_info["aid"])),
            "cid": CId(str(item["cid"])),
            "title": video_title,
            "pubdate": video_pubdate,  # 添加发布时间
            "path": Path(f"{video_title}/{part_name}")
        })
    
    return {"title": video_title, "videos": videos}


async def get_bangumi_info(fetcher: Fetcher, season_id: SeasonId) -> Dict[str, Any]:
    """获取番剧信息"""
    api = f"https://api.bilibili.com/pgc/web/season/section?season_id={season_id}"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取番剧 {season_id} 信息: {res_json.get('message') if res_json else 'Unknown error'}")
    
    return res_json["data"]


async def get_bangumi_list(fetcher: Fetcher, season_id: SeasonId) -> VideoListData:
    """获取番剧剧集列表"""
    bangumi_info = await get_bangumi_info(fetcher, season_id)
    title = bangumi_info["title"]
    
    videos = []
    if "episodes" in bangumi_info:
        for i, episode in enumerate(bangumi_info["episodes"]):
            videos.append({
                "id": i + 1,
                "name": episode.get("long_title", episode.get("title", f"第{i+1}集")),
                "avid": BvId(episode["bvid"]),
                "cid": CId(str(episode["cid"])),
                "title": title,
                "path": Path(f"{title}/{episode.get('long_title', episode.get('title', f'第{i+1}集'))}")
            })
    
    return {"title": title, "videos": videos}


async def convert_episode_to_season(fetcher: Fetcher, episode_id: EpisodeId) -> SeasonId:
    """将集数ID转换为季度ID"""
    api = f"https://api.bilibili.com/pgc/web/season/section?ep_id={episode_id}"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取剧集 {episode_id} 的季度信息")
    
    return SeasonId(str(res_json["data"]["season_id"]))


async def convert_media_to_season(fetcher: Fetcher, media_id: MediaId) -> SeasonId:
    """将媒体ID转换为季度ID"""
    api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取媒体 {media_id} 的季度信息")
    
    return SeasonId(str(res_json["data"]["media"]["season_id"]))


async def get_favourite_info(fetcher: Fetcher, fid: FId) -> Dict[str, Any]:
    """获取收藏夹信息"""
    api = f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={fid}"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取收藏夹 {fid} 信息: {res_json.get('message') if res_json else 'Unknown error'}")
    
    return res_json["data"]


async def get_favourite_avids(fetcher: Fetcher, fid: FId) -> List[AvId]:
    """获取收藏夹视频ID列表"""
    api = f"https://api.bilibili.com/x/v3/fav/resource/ids?media_id={fid}"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取收藏夹 {fid} 视频列表")
    
    return [BvId(video_info["bvid"]) for video_info in res_json["data"]]


async def get_user_space_videos(fetcher: Fetcher, mid: MId, max_pages: int = 5) -> List[AvId]:
    """获取用户空间视频列表"""
    api = "https://api.bilibili.com/x/space/wbi/arc/search"
    ps = 30  # 每页数量
    pn = 1
    all_avids = []
    
    while pn <= max_pages:
        params = {
            "mid": mid,
            "ps": ps,
            "tid": 0,
            "pn": pn,
            "order": "pubdate",
        }
        
        res_json = await fetcher.fetch_json(api, params)
        if not res_json or res_json.get("code") != 0:
            break
        
        vlist = res_json["data"]["list"]["vlist"]
        if not vlist:
            break
        
        all_avids.extend([BvId(video["bvid"]) for video in vlist])
        
        # 检查是否还有更多页面
        total_count = res_json["data"]["page"]["count"]
        if len(all_avids) >= total_count:
            break
        
        pn += 1
    
    return all_avids


async def get_series_videos(fetcher: Fetcher, series_id: SeriesId, mid: MId) -> List[AvId]:
    """获取视频列表/合集视频"""
    api = f"https://api.bilibili.com/x/series/archives?mid={mid}&series_id={series_id}&only_normal=true&pn=1&ps=30"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取视频列表 {series_id}")
    
    return [BvId(video["bvid"]) for video in res_json["data"]["archives"]]


async def get_watch_later_avids(fetcher: Fetcher) -> List[AvId]:
    """获取稍后再看列表"""
    api = "https://api.bilibili.com/x/v2/history/toview/web"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json:
        raise Exception("无法获取稍后再看列表")
    
    if res_json.get("code") in [-101, -400]:
        raise Exception("账号未登录，无法获取稍后再看列表")
    
    if res_json.get("code") != 0:
        raise Exception(f"获取稍后再看列表失败: {res_json.get('message')}")
    
    return [BvId(video["bvid"]) for video in res_json["data"]["list"]] 