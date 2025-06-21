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


async def get_bangumi_list(fetcher: Fetcher, season_id: str) -> Dict[str, Any]:
    """获取番剧剧集列表"""
    list_api = f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}"
    resp_json = await fetcher.fetch_json(list_api)
    
    if not resp_json:
        raise Exception(f"无法解析该番剧列表，season_id: {season_id}")
    if resp_json.get("result") is None:
        raise Exception(f"无法解析该番剧列表，season_id: {season_id}，原因：{resp_json.get('message')}")
    
    result = resp_json["result"]
    
    # 处理专区内容
    section_episodes = []
    for section in result.get("section", []):
        if section["type"] != 5:
            section_episodes += section["episodes"]
    
    # 构建剧集列表
    pages = []
    all_episodes = result["episodes"] + section_episodes
    
    for i, item in enumerate(all_episodes):
        episode_title = _bangumi_episode_title(item["title"], item["long_title"])
        pages.append({
            "id": i + 1,
            "name": episode_title,
            "cid": CId(str(item["cid"])),
            "episode_id": str(item["id"]),
            "avid": BvId(item["bvid"]),
            "is_section": i >= len(result["episodes"]),
            "is_preview": item.get("badge") == "预告",
            "title": episode_title,
            "pubdate": 0,  # 番剧没有pubdate概念
            "author": result.get("actor", {}).get("info", ""),
            "duration": 0  # 番剧duration需要从播放页面获取
        })
    
    return {
        "title": result["title"],
        "pages": pages
    }


def _bangumi_episode_title(title: str, extra_title: str) -> str:
    """格式化番剧剧集标题"""
    title_parts = []
    
    if re.match(r"^\d*\.?\d*$", title):
        title_parts.append(f"第{title}话")
    else:
        title_parts.append(title)
    
    if extra_title:
        title_parts.append(extra_title)
    
    return " ".join(title_parts)


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


async def get_favourite_avids(fetcher: Fetcher, fid: FId) -> List[Dict[str, Any]]:
    """获取收藏夹视频列表（包含基本信息）"""
    all_videos = []
    pn = 1
    ps = 20  # 每页数量
    
    while True:
        api = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn={pn}&ps={ps}"
        res_json = await fetcher.fetch_json(api)
        
        if not res_json or res_json.get("code") != 0:
            if pn == 1:  # 第一页失败，抛出异常
                raise Exception(f"无法获取收藏夹 {fid} 视频列表")
            else:  # 后续页面失败，可能是没有更多数据
                break
        
        medias = res_json["data"]["medias"]
        if not medias:
            break
        
        for video_info in medias:
            all_videos.append({
                "avid": BvId(video_info["bvid"]),
                "title": video_info.get("title", ""),
                "pubdate": video_info.get("pubtime", 0),
                "duration": video_info.get("duration", 0),
                "author": video_info.get("upper", {}).get("name", "")
            })
        
        # 检查是否还有更多页面
        data = res_json["data"]
        if data.get("has_more", False):
            pn += 1
            # 添加延迟避免请求过快
            import asyncio
            await asyncio.sleep(0.5)
        else:
            break
    
    Logger.info(f"收藏夹 {fid} 共获取到 {len(all_videos)} 个视频")
    return all_videos


async def get_user_space_videos(fetcher: Fetcher, mid: MId, max_pages: int = 5) -> List[Dict[str, Any]]:
    """获取用户空间视频列表（包含基本信息）"""
    api = "https://api.bilibili.com/x/space/wbi/arc/search"
    ps = 30  # 每页数量
    pn = 1
    all_videos = []
    
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
        
        for video in vlist:
            all_videos.append({
                "avid": BvId(video["bvid"]),
                "title": video.get("title", ""),
                "pubdate": video.get("created", 0),
                "duration": video.get("length", ""),
                "author": video.get("author", "")
            })
        
        # 检查是否还有更多页面
        total_count = res_json["data"]["page"]["count"]
        if len(all_videos) >= total_count:
            break
        
        pn += 1
    
    return all_videos


async def get_series_videos(fetcher: Fetcher, series_id: SeriesId, mid: MId) -> List[Dict[str, Any]]:
    """获取视频列表/合集视频（包含基本信息）"""
    api = f"https://api.bilibili.com/x/series/archives?mid={mid}&series_id={series_id}&only_normal=true&pn=1&ps=30"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取视频列表 {series_id}")
    
    videos = []
    for video in res_json["data"]["archives"]:
        videos.append({
            "avid": BvId(video["bvid"]),
            "title": video.get("title", ""),
            "pubdate": video.get("pubdate", 0),
            "duration": video.get("duration", 0),
            "author": video.get("owner", {}).get("name", "")
        })
    
    return videos


async def get_watch_later_avids(fetcher: Fetcher) -> List[Dict[str, Any]]:
    """获取稍后再看列表（包含基本信息）"""
    api = "https://api.bilibili.com/x/v2/history/toview/web"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json:
        raise Exception("无法获取稍后再看列表")
    
    if res_json.get("code") in [-101, -400]:
        raise Exception("账号未登录，无法获取稍后再看列表")
    
    if res_json.get("code") != 0:
        raise Exception(f"获取稍后再看列表失败: {res_json.get('message')}")
    
    videos = []
    for video in res_json["data"]["list"]:
        videos.append({
            "avid": BvId(video["bvid"]),
            "title": video.get("title", ""),
            "pubdate": video.get("pubdate", 0),
            "duration": video.get("duration", 0),
            "author": video.get("owner", {}).get("name", "")
        })
    
    return videos


async def get_season_id_by_media_id(fetcher: Fetcher, media_id: str) -> str:
    """通过media_id获取season_id"""
    media_api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
    res_json = await fetcher.fetch_json(media_api)
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取番剧信息，media_id: {media_id}")
    return str(res_json["result"]["media"]["season_id"])


async def get_season_id_by_episode_id(fetcher: Fetcher, episode_id: str) -> str:
    """通过episode_id获取season_id"""
    episode_api = f"https://api.bilibili.com/pgc/view/web/season?ep_id={episode_id}"
    res_json = await fetcher.fetch_json(episode_api)
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取番剧信息，episode_id: {episode_id}")
    return str(res_json["result"]["season_id"]) 