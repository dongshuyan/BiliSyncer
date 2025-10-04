"""
B站API接口
"""

import re
import hashlib
import time
import urllib.parse
from typing import Any, Dict, List, Optional, cast, Tuple
from utils.types import *
from utils.fetcher import Fetcher
from utils.logger import Logger
import asyncio


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
    
    page_data = cast(List[Any], res_json["data"])
    total_pages = len(page_data)
    
    # 如果是多P视频（分P数量 > 1），只返回一个条目，标记为多P视频
    if total_pages > 1:
        Logger.info(f"检测到多P视频: {video_title} (共{total_pages}P)")
        videos = [{
            "id": 1,
            "name": f"{video_title} (共{total_pages}P)",
            "avid": BvId(video_info["bvid"]) if video_info.get("bvid") else AId(str(video_info["aid"])),
            "cid": CId(str(page_data[0]["cid"])),  # 使用第一P的CID
            "title": video_title,
            "pubdate": video_pubdate,
            "path": Path(video_title),  # 多P视频使用视频标题作为文件夹
            "is_multi_part": True,  # 标记为多P视频
            "total_parts": total_pages  # 记录总分P数量
        }]
    else:
        # 单P视频，使用原有逻辑
        item = page_data[0]
        part_name = item["part"]
        if not part_name or part_name in ["", "未命名"]:
            part_name = video_title
        
        videos = [{
            "id": 1,
            "name": part_name,
            "avid": BvId(video_info["bvid"]) if video_info.get("bvid") else AId(str(video_info["aid"])),
            "cid": CId(str(item["cid"])),
            "title": video_title,
            "pubdate": video_pubdate,
            "path": Path(f"{video_title}/{part_name}"),
            "is_multi_part": False,  # 标记为单P视频
            "total_parts": 1
        }]
    
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
            "duration": 0,  # 番剧duration需要从播放页面获取
            "is_multi_part": False,  # 番剧每集都是单独的，不是多P视频
            "total_parts": 1  # 每集只有1个部分
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


async def get_favourite_avids(fetcher: Fetcher, fid: FId) -> List[AvId]:
    """获取收藏夹视频URL列表（仅获取ID，不获取详细信息）- 带重试机制"""
    Logger.info(f"获取收藏夹 {fid} 的视频列表...")
    
    all_avids = []
    pn = 1
    ps = 20  # 每页数量
    max_retries = 3
    base_delay = 1.0
    
    while True:
        api = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn={pn}&ps={ps}"
        
        # 带重试的请求
        success = False
        for attempt in range(max_retries):
            try:
                res_json = await fetcher.fetch_json(api)
                
                if not res_json or res_json.get("code") != 0:
                    if pn == 1 and attempt == max_retries - 1:  # 第一页失败，抛出异常
                        raise Exception(f"无法获取收藏夹 {fid} 视频列表")
                    elif pn > 1:  # 后续页面失败，可能是没有更多数据
                        Logger.info(f"页面 {pn} 获取失败，结束获取")
                        success = True
                        break
                    else:
                        delay = base_delay * (attempt + 1)
                        Logger.warning(f"获取收藏夹页面失败 (页面 {pn}，尝试 {attempt + 1}/{max_retries})，等待 {delay:.1f} 秒后重试...")
                        await asyncio.sleep(delay)
                        continue
                
                success = True
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)
                    Logger.warning(f"获取收藏夹异常 (页面 {pn}，尝试 {attempt + 1}/{max_retries}): {e}，等待 {delay:.1f} 秒后重试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    if pn == 1:
                        raise Exception(f"获取收藏夹 {fid} 视频列表失败: {e}")
                    else:
                        Logger.info(f"页面 {pn} 最终失败，结束获取")
                        success = True
                        break
        
        if not success:
            break
        
        if res_json and res_json.get("code") == 0:
            medias = res_json["data"]["medias"]
            if not medias:
                break
            
            # 只添加视频ID
            for video_info in medias:
                all_avids.append(BvId(video_info["bvid"]))
            
            # 检查是否还有更多页面
            data = res_json["data"]
            if data.get("has_more", False):
                pn += 1
                # 添加延迟避免请求过快
                await asyncio.sleep(0.5)
            else:
                break
        else:
            break
    
    Logger.info(f"收藏夹 {fid} 共获取到 {len(all_avids)} 个视频ID")
    return all_avids


async def get_favourite_avids_incremental(fetcher: Fetcher, fid: FId, existing_urls: set) -> List[AvId]:
    """增量获取收藏夹视频列表（支持实时查重，发现重复时停止获取）"""
    Logger.info(f"增量获取收藏夹 {fid} 的视频列表...")
    
    new_avids = []
    pn = 1
    ps = 20  # 每页数量
    max_retries = 3
    base_delay = 1.0
    duplicate_found = False
    
    while not duplicate_found:
        api = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn={pn}&ps={ps}"
        
        # 带重试的请求
        success = False
        for attempt in range(max_retries):
            try:
                res_json = await fetcher.fetch_json(api)
                
                if not res_json or res_json.get("code") != 0:
                    if pn == 1 and attempt == max_retries - 1:  # 第一页失败，抛出异常
                        raise Exception(f"无法获取收藏夹 {fid} 视频列表")
                    elif pn > 1:  # 后续页面失败，可能是没有更多数据
                        Logger.info(f"页面 {pn} 获取失败，结束获取")
                        success = True
                        break
                    else:
                        delay = base_delay * (attempt + 1)
                        Logger.warning(f"获取收藏夹页面失败 (页面 {pn}，尝试 {attempt + 1}/{max_retries})，等待 {delay:.1f} 秒后重试...")
                        await asyncio.sleep(delay)
                        continue
                
                success = True
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)
                    Logger.warning(f"获取收藏夹异常 (页面 {pn}，尝试 {attempt + 1}/{max_retries}): {e}，等待 {delay:.1f} 秒后重试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    if pn == 1:
                        raise Exception(f"获取收藏夹 {fid} 视频列表失败: {e}")
                    else:
                        Logger.info(f"页面 {pn} 最终失败，结束获取")
                        success = True
                        break
        
        if not success:
            break
        
        if res_json and res_json.get("code") == 0:
            medias = res_json["data"]["medias"]
            if not medias:
                break
            
            # 实时查重：检查当前页面的视频是否已存在
            page_new_avids = []
            for video_info in medias:
                bvid = BvId(video_info["bvid"])
                video_url = bvid.to_url()
                
                if video_url in existing_urls:
                    # 发现重复，停止获取
                    Logger.info(f"发现重复视频 {bvid}，停止获取（已获取 {len(new_avids)} 个新视频）")
                    duplicate_found = True
                    break
                else:
                    # 新视频，添加到列表
                    page_new_avids.append(bvid)
                    new_avids.append(bvid)
            
            # 如果当前页面有重复，不再处理后续页面
            if duplicate_found:
                break
            
            # 检查是否还有更多页面
            data = res_json["data"]
            if data.get("has_more", False):
                pn += 1
                # 添加延迟避免请求过快
                await asyncio.sleep(0.5)
            else:
                break
        else:
            break
    
    if duplicate_found:
        Logger.info(f"增量获取完成：发现重复视频，共获取到 {len(new_avids)} 个新视频")
    else:
        Logger.info(f"增量获取完成：收藏夹 {fid} 共获取到 {len(new_avids)} 个新视频")
    
    return new_avids


async def get_user_space_videos(fetcher: Fetcher, mid: MId) -> List[AvId]:
    """获取用户空间视频URL列表（仅获取ID，不获取详细信息）- 带重试机制"""
    Logger.info(f"获取用户 {mid} 的投稿视频列表...")
    
    max_retries = 10
    base_delay = 2.0
    
    # 获取WBI签名信息
    wbi_img = await get_wbi_img(fetcher)
    
    space_videos_api = "https://api.bilibili.com/x/space/wbi/arc/search"
    ps = 30  # 每页数量
    pn = 1
    total_pages = 1
    all_avids = []
    
    while pn <= total_pages:
        # 构建参数
        params = {
            "mid": str(mid),
            "ps": ps,
            "tid": 0,
            "pn": pn,
            "order": "pubdate",
        }
        
        # 应用WBI签名
        signed_params = encode_wbi(params, wbi_img)
        
        # 带重试机制的请求
        success = False
        for attempt in range(max_retries):
            try:
                # 发起请求
                res_json = await fetcher.fetch_json(space_videos_api, signed_params)
                
                if not res_json:
                    raise Exception("无响应")
                
                if res_json.get("code") == -352:
                    # 风控校验失败，需要重试
                    delay = base_delay * (2 ** attempt)  # 指数退避
                    Logger.warning(f"风控校验失败 (页面 {pn}，尝试 {attempt + 1}/{max_retries})，等待 {delay:.1f} 秒后重试...")
                    await asyncio.sleep(delay)
                    continue
                elif res_json.get("code") != 0:
                    if pn == 1 and attempt == max_retries - 1:
                        Logger.error(f"无法获取用户 {mid} 的投稿视频: {res_json.get('message')}")
                        return []
                    elif pn > 1:
                        # 后续页面失败，可能没有更多数据
                        Logger.info(f"页面 {pn} 获取失败，结束获取")
                        success = True
                        break
                    else:
                        delay = base_delay * (attempt + 1)
                        Logger.warning(f"请求失败 (页面 {pn}，尝试 {attempt + 1}/{max_retries})，等待 {delay:.1f} 秒后重试...")
                        await asyncio.sleep(delay)
                        continue
                
                # 成功获取数据
                success = True
                break
                
            except Exception as e:
                Logger.warning(f"请求异常 (页面 {pn}，尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    if pn == 1:
                        Logger.error(f"获取用户 {mid} 投稿视频最终失败")
                        return []
                    else:
                        Logger.info(f"页面 {pn} 最终失败，结束获取")
                        success = True
                        break
        
        if not success:
            break
        
        # 解析数据，只获取BVID
        if res_json and res_json.get("code") == 0:
            data = res_json.get("data", {})
            list_data = data.get("list", {})
            vlist = list_data.get("vlist", [])
            
            if not vlist:
                break
            
            # 只添加视频ID
            for video in vlist:
                all_avids.append(BvId(video["bvid"]))
            
            # 计算总页数
            page_info = data.get("page", {})
            total_count = page_info.get("count", 0)
            total_pages = (total_count + ps - 1) // ps  # 向上取整
            
            Logger.debug(f"已获取第 {pn}/{total_pages} 页，共 {len(vlist)} 个视频ID")
        
        pn += 1
        
        # 添加延迟避免请求过快
        if pn <= total_pages:
            await asyncio.sleep(0.5)
    
    Logger.info(f"用户 {mid} 共获取到 {len(all_avids)} 个投稿视频ID")
    return all_avids


async def get_user_space_videos_incremental(fetcher: Fetcher, mid: MId, existing_urls: set) -> List[AvId]:
    """增量获取用户空间视频列表（支持实时查重，发现重复时停止获取）"""
    Logger.info(f"增量获取用户 {mid} 的投稿视频列表...")
    
    max_retries = 10
    base_delay = 2.0
    
    # 获取WBI签名信息
    wbi_img = await get_wbi_img(fetcher)
    
    space_videos_api = "https://api.bilibili.com/x/space/wbi/arc/search"
    ps = 30  # 每页数量
    pn = 1
    total_pages = 1
    new_avids = []
    duplicate_found = False
    
    while pn <= total_pages and not duplicate_found:
        # 构建参数
        params = {
            "mid": str(mid),
            "ps": ps,
            "tid": 0,
            "pn": pn,
            "order": "pubdate",
        }
        
        # 应用WBI签名
        signed_params = encode_wbi(params, wbi_img)
        
        # 带重试机制的请求
        success = False
        for attempt in range(max_retries):
            try:
                # 发起请求
                res_json = await fetcher.fetch_json(space_videos_api, signed_params)
                
                if not res_json:
                    raise Exception("无响应")
                
                if res_json.get("code") == -352:
                    # 风控校验失败，需要重试
                    delay = base_delay * (2 ** attempt)  # 指数退避
                    Logger.warning(f"风控校验失败 (页面 {pn}，尝试 {attempt + 1}/{max_retries})，等待 {delay:.1f} 秒后重试...")
                    await asyncio.sleep(delay)
                    continue
                elif res_json.get("code") != 0:
                    if pn == 1 and attempt == max_retries - 1:
                        Logger.error(f"无法获取用户 {mid} 的投稿视频: {res_json.get('message')}")
                        return []
                    elif pn > 1:
                        # 后续页面失败，可能没有更多数据
                        Logger.info(f"页面 {pn} 获取失败，结束获取")
                        success = True
                        break
                    else:
                        delay = base_delay * (attempt + 1)
                        Logger.warning(f"请求失败 (页面 {pn}，尝试 {attempt + 1}/{max_retries})，等待 {delay:.1f} 秒后重试...")
                        await asyncio.sleep(delay)
                        continue
                
                # 成功获取数据
                success = True
                break
                
            except Exception as e:
                Logger.warning(f"请求异常 (页面 {pn}，尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    if pn == 1:
                        Logger.error(f"获取用户 {mid} 投稿视频最终失败")
                        return []
                    else:
                        Logger.info(f"页面 {pn} 最终失败，结束获取")
                        success = True
                        break
        
        if not success:
            break
        
        # 解析数据并实时查重
        if res_json and res_json.get("code") == 0:
            data = res_json.get("data", {})
            list_data = data.get("list", {})
            vlist = list_data.get("vlist", [])
            
            if not vlist:
                break
            
            # 实时查重：检查当前页面的视频是否已存在
            page_new_avids = []
            for video in vlist:
                bvid = BvId(video["bvid"])
                video_url = bvid.to_url()
                
                if video_url in existing_urls:
                    # 发现重复，停止获取
                    Logger.info(f"发现重复视频 {bvid}，停止获取（已获取 {len(new_avids)} 个新视频）")
                    duplicate_found = True
                    break
                else:
                    # 新视频，添加到列表
                    page_new_avids.append(bvid)
                    new_avids.append(bvid)
            
            # 如果当前页面有重复，不再处理后续页面
            if duplicate_found:
                break
            
            # 计算总页数
            page_info = data.get("page", {})
            total_count = page_info.get("count", 0)
            total_pages = (total_count + ps - 1) // ps  # 向上取整
            
            Logger.debug(f"已获取第 {pn}/{total_pages} 页，新增 {len(page_new_avids)} 个视频ID")
        
        pn += 1
        
        # 添加延迟避免请求过快
        if pn <= total_pages and not duplicate_found:
            await asyncio.sleep(0.5)
    
    if duplicate_found:
        Logger.info(f"增量获取完成：发现重复视频，共获取到 {len(new_avids)} 个新视频")
    else:
        Logger.info(f"增量获取完成：用户 {mid} 共获取到 {len(new_avids)} 个新视频")
    
    return new_avids


# WBI签名相关变量
wbi_img_cache = None

async def get_wbi_img(fetcher: Fetcher) -> Dict[str, str]:
    """获取WBI签名所需的img_key和sub_key（带重试机制）"""
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            # 先访问bilibili主页
            await fetcher.get_redirected_url("https://www.bilibili.com")
            
            # 获取用户基本信息页面
            api = "https://api.bilibili.com/x/web-interface/nav"
            res_json = await fetcher.fetch_json(api)
            
            if not res_json or res_json.get("code") != 0:
                if attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)
                    Logger.warning(f"获取WBI签名信息失败 (尝试 {attempt + 1}/{max_retries})，{delay:.1f}秒后重试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception(f"获取WBI签名信息失败: {res_json.get('message') if res_json else 'No response'}")
            
            # 提取wbi相关字段
            data = res_json["data"]
            wbi_img_data = data["wbi_img"]
            img_url = wbi_img_data["img_url"]
            sub_url = wbi_img_data["sub_url"]
            
            # 提取文件名（去掉路径和扩展名）
            img_key = img_url.split("/")[-1].split(".")[0]
            sub_key = sub_url.split("/")[-1].split(".")[0]
            
            Logger.debug(f"获取WBI签名密钥: img_key={img_key[:8]}..., sub_key={sub_key[:8]}...")
            return {"img_key": img_key, "sub_key": sub_key}
            
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (attempt + 1)
                Logger.warning(f"获取WBI签名信息异常 (尝试 {attempt + 1}/{max_retries}): {e}，{delay:.1f}秒后重试...")
                await asyncio.sleep(delay)
                continue
            else:
                Logger.error(f"获取WBI签名信息最终失败: {e}")
                raise Exception(f"获取WBI签名信息最终失败: {e}")
    
    # 这行不应该被执行，但为了类型检查
    raise Exception("获取WBI签名信息失败")


async def get_wbi_img_yutto_style(fetcher: Fetcher) -> Dict[str, str]:
    """获取WBI签名所需的img_key和sub_key（yutto风格，使用缓存机制）"""
    global wbi_img_cache
    if wbi_img_cache is not None:
        return wbi_img_cache
    
    # 获取用户基本信息页面
    api = "https://api.bilibili.com/x/web-interface/nav"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json:
        raise Exception("获取WBI签名信息失败: 无响应")
    
    if res_json.get("code") != 0:
        raise Exception(f"获取WBI签名信息失败: {res_json.get('message', 'Unknown error')}")
    
    # 提取wbi相关字段
    data = res_json["data"]
    wbi_img_data = data["wbi_img"]
    img_url = wbi_img_data["img_url"]
    sub_url = wbi_img_data["sub_url"]
    
    # 提取文件名（去掉路径和扩展名）
    img_key = img_url.split("/")[-1].split(".")[0]
    sub_key = sub_url.split("/")[-1].split(".")[0]
    
    wbi_img_cache = {"img_key": img_key, "sub_key": sub_key}
    Logger.debug(f"获取WBI签名密钥(yutto风格): img_key={img_key[:8]}..., sub_key={sub_key[:8]}...")
    return wbi_img_cache


def _get_mixin_key(string: str) -> str:
    """生成混合密钥"""
    char_indices = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5,
        49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55,
        40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57,
        62, 11, 36, 20, 34, 44, 52,
    ]
    return "".join([string[idx] for idx in char_indices[:32] if idx < len(string)])


def encode_wbi(params: Dict[str, Any], wbi_img: Dict[str, str]) -> Dict[str, Any]:
    """WBI签名编码"""
    import re
    
    img_key = wbi_img.get("img_key", "")
    sub_key = wbi_img.get("sub_key", "")
    
    if not img_key or not sub_key:
        Logger.warning("WBI密钥不完整，跳过签名")
        return params
    
    illegal_char_remover = re.compile(r"[!'\(\)*]")
    
    mixin_key = _get_mixin_key(img_key + sub_key)
    time_stamp = int(time.time())
    params_with_wts = dict(params, wts=time_stamp)
    
    # URL编码并排序
    url_encoded_params = urllib.parse.urlencode(
        {
            key: illegal_char_remover.sub("", str(params_with_wts[key]))
            for key in sorted(params_with_wts.keys())
        }
    )
    
    # 计算w_rid
    w_rid = hashlib.md5((url_encoded_params + mixin_key).encode()).hexdigest()
    all_params = dict(params_with_wts, w_rid=w_rid)
    return all_params


def encode_wbi_yutto_style(params: Dict[str, Any], wbi_img: Dict[str, str]) -> Dict[str, Any]:
    """WBI签名编码（yutto风格，包含dm参数）"""
    import re
    import base64
    import random
    import string
    
    img_key = wbi_img.get("img_key", "")
    sub_key = wbi_img.get("sub_key", "")
    
    if not img_key or not sub_key:
        Logger.warning("WBI密钥不完整，跳过签名")
        return params
    
    illegal_char_remover = re.compile(r"[!'\(\)*]")
    
    mixin_key = _get_mixin_key(img_key + sub_key)
    time_stamp = int(time.time())
    params_with_wts = dict(params, wts=time_stamp)
    
    # 生成随机dm参数（模拟yutto的实现）
    dm_img_str = base64.b64encode("".join(random.choices(string.printable, k=random.randint(16, 64))).encode())[:-2].decode()
    dm_cover_img_str = base64.b64encode("".join(random.choices(string.printable, k=random.randint(32, 128))).encode())[:-2].decode()
    
    # 添加必要的参数
    params_with_dm = {
        **params_with_wts,
        "dm_img_list": "[]",
        "dm_img_str": dm_img_str,
        "dm_cover_img_str": dm_cover_img_str,
    }
    
    # URL编码并排序
    url_encoded_params = urllib.parse.urlencode(
        {
            key: illegal_char_remover.sub("", str(params_with_dm[key]))
            for key in sorted(params_with_dm.keys())
        }
    )
    
    # 计算w_rid
    w_rid = hashlib.md5((url_encoded_params + mixin_key).encode()).hexdigest()
    all_params = dict(params_with_dm, w_rid=w_rid)
    return all_params


async def get_user_name(fetcher: Fetcher, mid: MId) -> str:
    """获取用户名（每轮尝试两种方法）"""
    Logger.info(f"获取用户 {mid} 的用户名...")
    
    max_rounds = 30  # 30轮尝试
    
    for round_num in range(max_rounds):
        round_start = round_num + 1
        
        # 第一次尝试：yutto风格方法（优先使用，成功率更高）
        try:
            Logger.debug(f"第{round_start}轮-yutto风格: 获取WBI签名...")
            wbi_img = await get_wbi_img_yutto_style(fetcher)
            params = {"mid": str(mid)}
            signed_params = encode_wbi_yutto_style(params, wbi_img)
            
            space_info_api = "https://api.bilibili.com/x/space/wbi/acc/info"
            await fetcher.touch_url("https://www.bilibili.com")
            
            user_info = await fetcher.fetch_json(space_info_api, signed_params)
            
            if not user_info:
                raise Exception("无响应")
            
            if user_info.get("code") == -404:
                Logger.warning(f"用户 {mid} 不存在，疑似注销或被封禁")
                return f"用户{mid}"
            elif user_info.get("code") == -352:
                # 风控校验失败，准备下一轮
                Logger.warning(f"第{round_start}轮-yutto风格: 风控校验失败，准备下一轮...")
                raise Exception("风控校验失败")
            elif user_info.get("code") != 0:
                error_msg = user_info.get('message', 'Unknown error')
                Logger.warning(f"第{round_start}轮-yutto风格: API错误 {error_msg}，准备下一轮...")
                raise Exception(f"API错误: {error_msg}")
            else:
                # 成功获取用户信息
                username = user_info.get("data", {}).get("name", f"用户{mid}")
                Logger.info(f"用户 {mid} 的用户名: {username} (第{round_start}轮-yutto风格成功)")
                return username
                
        except Exception as e:
            Logger.debug(f"第{round_start}轮-yutto风格失败: {e}")
        
        # 第二次尝试：原有方法（备用方案）
        try:
            Logger.debug(f"第{round_start}轮-原有方法: 获取WBI签名...")
            wbi_img = await get_wbi_img(fetcher)
            params = {"mid": str(mid)}
            signed_params = encode_wbi(params, wbi_img)
            
            space_info_api = "https://api.bilibili.com/x/space/wbi/acc/info"
            await fetcher.get_redirected_url("https://www.bilibili.com")
            
            user_info = await fetcher.fetch_json(space_info_api, signed_params)
            
            if not user_info:
                raise Exception("无响应")
            
            if user_info.get("code") == -404:
                Logger.warning(f"用户 {mid} 不存在，疑似注销或被封禁")
                return f"用户{mid}"
            elif user_info.get("code") == -352:
                # 风控校验失败，准备下一轮
                Logger.warning(f"第{round_start}轮-原有方法: 风控校验失败，准备下一轮...")
                raise Exception("风控校验失败")
            elif user_info.get("code") != 0:
                error_msg = user_info.get('message', 'Unknown error')
                Logger.warning(f"第{round_start}轮-原有方法: API错误 {error_msg}，准备下一轮...")
                raise Exception(f"API错误: {error_msg}")
            else:
                # 成功获取用户信息
                username = user_info.get("data", {}).get("name", f"用户{mid}")
                Logger.info(f"用户 {mid} 的用户名: {username} (第{round_start}轮-原有方法成功)")
                return username
                
        except Exception as e:
            Logger.debug(f"第{round_start}轮-原有方法失败: {e}")
        
        # 本轮两种方法都失败，等待后进入下一轮
        if round_num < max_rounds - 1:  # 不是最后一轮
            delay = round_start * 1.0  # 每轮增加1秒
            Logger.warning(f"第{round_start}轮失败，等待 {delay:.1f} 秒后进入下一轮...")
            await asyncio.sleep(delay)
    
    # 30轮都失败了
    Logger.error(f"获取用户名最终失败，已尝试 {max_rounds} 轮")
    return f"用户{mid}"


async def get_series_videos(fetcher: Fetcher, series_id: SeriesId, mid: MId) -> List[AvId]:
    """获取视频列表/合集URL列表（仅获取ID，不获取详细信息）"""
    api = f"https://api.bilibili.com/x/series/archives?mid={mid}&series_id={series_id}&only_normal=true&pn=1&ps=30"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取视频列表 {series_id}")
    
    avids = []
    for video in res_json["data"]["archives"]:
        avids.append(BvId(video["bvid"]))
    
    Logger.info(f"视频列表 {series_id} 共获取到 {len(avids)} 个视频ID")
    return avids


async def get_watch_later_avids(fetcher: Fetcher) -> List[AvId]:
    """获取稍后再看URL列表（仅获取ID，不获取详细信息）"""
    api = "https://api.bilibili.com/x/v2/history/toview/web"
    res_json = await fetcher.fetch_json(api)
    
    if not res_json:
        raise Exception("无法获取稍后再看列表")
    
    if res_json.get("code") in [-101, -400]:
        raise Exception("账号未登录，无法获取稍后再看列表")
    
    if res_json.get("code") != 0:
        raise Exception(f"获取稍后再看列表失败: {res_json.get('message')}")
    
    avids = []
    for video in res_json["data"]["list"]:
        avids.append(BvId(video["bvid"]))
    
    Logger.info(f"稍后再看共获取到 {len(avids)} 个视频ID")
    return avids


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


async def get_bangumi_episode_list(fetcher: Fetcher, season_id: str) -> Tuple[str, List[str]]:
    """获取番剧剧集ID列表（仅获取ID，不获取详细信息）"""
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
    
    # 获取剧集ID列表
    episode_ids = []
    all_episodes = result["episodes"] + section_episodes
    
    for item in all_episodes:
        episode_ids.append(str(item["id"]))  # 使用episode_id
    
    bangumi_title = result["title"]
    Logger.info(f"番剧 {bangumi_title} 共获取到 {len(episode_ids)} 个剧集ID")
    
    return bangumi_title, episode_ids 


async def get_bangumi_episode_info(fetcher: Fetcher, episode_id: str) -> Dict[str, Any]:
    """获取单个番剧剧集的详细信息"""
    # 通过episode_id获取剧集详细信息
    episode_api = f"https://api.bilibili.com/pgc/view/web/season?ep_id={episode_id}"
    resp_json = await fetcher.fetch_json(episode_api)
    
    if not resp_json or resp_json.get("result") is None:
        raise Exception(f"无法获取剧集 {episode_id} 的详细信息")
    
    result = resp_json["result"]
    
    # 查找当前剧集
    current_episode = None
    all_episodes = result["episodes"] + [ep for section in result.get("section", []) for ep in section.get("episodes", [])]
    
    for episode in all_episodes:
        if str(episode["id"]) == episode_id:
            current_episode = episode
            break
    
    if not current_episode:
        raise Exception(f"无法找到剧集 {episode_id} 的信息")
    
    episode_title = _bangumi_episode_title(current_episode["title"], current_episode["long_title"])
    
    return {
        "avid": BvId(current_episode["bvid"]),
        "cid": CId(str(current_episode["cid"])),
        "title": episode_title,
        "name": episode_title,
        "pubdate": 0,  # 番剧没有pubdate概念
        "author": result.get("actor", {}).get("info", ""),
        "duration": 0,  # 番剧duration需要从播放页面获取
        "episode_id": episode_id,
        "is_preview": current_episode.get("badge") == "预告"
    } 


# 课程(Cheese)相关API
async def get_cheese_season_id_by_episode_id(fetcher: Fetcher, episode_id: str) -> str:
    """通过episode_id获取课程的season_id"""
    home_url = f"https://api.bilibili.com/pugv/view/web/season?ep_id={episode_id}"
    res_json = await fetcher.fetch_json(home_url)
    
    if not res_json or res_json.get("code") != 0:
        raise Exception(f"无法获取课程信息，episode_id: {episode_id}")
    
    return str(res_json["data"]["season_id"])


async def get_cheese_episode_list(fetcher: Fetcher, season_id: str) -> Tuple[str, List[str]]:
    """获取课程剧集ID列表（仅获取ID，不获取详细信息）"""
    list_api = f"https://api.bilibili.com/pugv/view/web/season?season_id={season_id}"
    resp_json = await fetcher.fetch_json(list_api)
    
    if not resp_json:
        raise Exception(f"无法解析该课程列表，season_id: {season_id}")
    if resp_json.get("data") is None:
        raise Exception(f"无法解析该课程列表，season_id: {season_id}，原因：{resp_json.get('message')}")
    
    result = resp_json["data"]
    
    # 获取课程剧集ID列表
    episode_ids = []
    for item in result["episodes"]:
        episode_ids.append(str(item["id"]))  # 使用episode_id
    
    course_title = result["title"]
    Logger.info(f"课程 {course_title} 共获取到 {len(episode_ids)} 个课时ID")
    
    return course_title, episode_ids


async def get_cheese_episode_info(fetcher: Fetcher, episode_id: str) -> Dict[str, Any]:
    """获取单个课程课时的详细信息"""
    # 先获取season_id
    season_id = await get_cheese_season_id_by_episode_id(fetcher, episode_id)
    
    # 通过season_id获取课程详细信息
    episode_api = f"https://api.bilibili.com/pugv/view/web/season?season_id={season_id}"
    resp_json = await fetcher.fetch_json(episode_api)
    
    if not resp_json or resp_json.get("data") is None:
        raise Exception(f"无法获取课时 {episode_id} 的详细信息")
    
    result = resp_json["data"]
    
    # 查找当前课时
    current_episode = None
    for episode in result["episodes"]:
        if str(episode["id"]) == episode_id:
            current_episode = episode
            break
    
    if not current_episode:
        raise Exception(f"无法找到课时 {episode_id} 的信息")
    
    episode_title = current_episode["title"]
    
    return {
        "avid": AId(str(current_episode["aid"])),
        "cid": CId(str(current_episode["cid"])),
        "title": episode_title,
        "name": episode_title,
        "pubdate": 0,  # 课程没有pubdate概念
        "author": result.get("up_info", {}).get("uname", ""),
        "duration": 0,  # 课程duration需要从播放页面获取
        "episode_id": episode_id
    } 