"""
HTTP请求工具类
"""

import asyncio
import httpx
from typing import Any, Dict, Optional
from .logger import Logger


class Fetcher:
    """HTTP请求工具"""
    
    def __init__(self, sessdata: Optional[str] = None, proxy: Optional[str] = None, max_retries: int = 3, retry_delay: float = 1.0):
        """初始化"""
        self.cookies = {}
        if sessdata:
            self.cookies["SESSDATA"] = sessdata
        
        self.proxy = proxy
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self._client = httpx.AsyncClient(
            cookies=self.cookies,
            proxy=self.proxy,
            timeout=httpx.Timeout(30.0, connect=10.0),  # 设置连接和总超时
            follow_redirects=False,  # 不自动跟随重定向
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com"
            },
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)  # 连接池限制
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self._client:
            await self._client.aclose()
    
    async def fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """获取JSON数据（带重试机制）"""
        if not self._client:
            raise RuntimeError("Fetcher not initialized. Use 'async with' syntax.")
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # 在重试时添加延迟
                if attempt > 0:
                    await asyncio.sleep(self.retry_delay * attempt)
                    Logger.debug(f"重试请求 ({attempt}/{self.max_retries}): {url}")
                
                response = await self._client.get(url, params=params)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    Logger.warning(f"请求频率限制 (429)，等待后重试: {url}")
                    await asyncio.sleep(5.0)  # 频率限制时等待更久
                    continue
                elif response.status_code in [502, 503, 504]:
                    Logger.warning(f"服务器暂时不可用 ({response.status_code})，重试: {url}")
                    continue
                else:
                    Logger.error(f"HTTP错误 {response.status_code}: {url}")
                    return None
                    
            except httpx.ReadTimeout as e:
                last_exception = e
                Logger.warning(f"读取超时 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
                continue
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last_exception = e
                Logger.warning(f"网络连接错误 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
                continue
            except Exception as e:
                last_exception = e
                Logger.error(f"请求失败: {e}")
                break
        
        # 所有重试都失败了
        Logger.error(f"请求最终失败 ({url})，已重试 {self.max_retries} 次")
        if last_exception:
            Logger.error(f"最后一次错误: {last_exception}")
        return None
    
    async def get_redirected_url(self, url: str) -> str:
        """获取重定向后的URL"""
        if not self._client:
            raise RuntimeError("Fetcher not initialized. Use 'async with' syntax.")
        
        try:
            # 临时创建一个支持重定向的客户端
            async with httpx.AsyncClient(
                cookies=self.cookies,
                proxy=self.proxy,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                    "Referer": "https://www.bilibili.com"
                }
            ) as client:
                response = await client.get(url)
                return str(response.url)
        except Exception as e:
            Logger.error(f"获取重定向URL失败: {e}")
            return url
    
    async def touch_url(self, url: str) -> bool:
        """访问URL（用于登录状态验证）"""
        if not self._client:
            raise RuntimeError("Fetcher not initialized. Use 'async with' syntax.")
        
        try:
            response = await self._client.get(url)
            return response.status_code == 200
        except Exception:
            return False 