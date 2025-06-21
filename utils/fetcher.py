"""
HTTP请求工具类
"""

import asyncio
import httpx
from typing import Any, Dict, Optional
from .logger import Logger


class Fetcher:
    """HTTP请求工具"""
    
    def __init__(self, sessdata: Optional[str] = None, proxy: Optional[str] = None):
        """初始化"""
        self.cookies = {}
        if sessdata:
            self.cookies["SESSDATA"] = sessdata
        
        self.proxy = proxy
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self._client = httpx.AsyncClient(
            cookies=self.cookies,
            proxy=self.proxy,
            timeout=30.0,
            follow_redirects=False,  # 不自动跟随重定向
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self._client:
            await self._client.aclose()
    
    async def fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """获取JSON数据"""
        if not self._client:
            raise RuntimeError("Fetcher not initialized. Use 'async with' syntax.")
        
        try:
            response = await self._client.get(url, params=params)
            if response.status_code != 200:
                Logger.error(f"HTTP错误 {response.status_code}: {url}")
                return None
            return response.json()
        except Exception as e:
            Logger.error(f"请求失败: {e}")
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
                timeout=30.0,
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