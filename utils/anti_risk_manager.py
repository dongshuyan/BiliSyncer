"""
风控管理器
用于检测和管理Bilibili的风控状态
"""

from typing import List, Dict, Any, Optional
from .logger import Logger
from .fetcher import Fetcher
from extractors import extract_video_list


class AntiRiskManager:
    """风控管理器"""
    
    def __init__(self):
        self.is_risk_controlled = False
        self.successful_urls: List[Dict[str, Any]] = []
        self.max_urls = 10  # 最多保存10个成功URL
    
    def add_successful_url(self, url: str, url_type: str) -> None:
        """添加成功的URL到测试列表"""
        # 检查是否已存在
        for item in self.successful_urls:
            if item['url'] == url:
                return
        
        # 添加新URL
        self.successful_urls.append({
            'url': url,
            'type': url_type,
            'timestamp': None  # 可以添加时间戳
        })
        
        # 保持列表长度不超过最大值
        if len(self.successful_urls) > self.max_urls:
            self.successful_urls.pop(0)
        
        Logger.debug(f"已添加成功URL: {url} (类型: {url_type})")
    
    async def check_risk_control(self, fetcher: Fetcher) -> bool:
        """检测是否受到风控"""
        if not self.successful_urls:
            Logger.warning("没有可用的测试URL，无法检测风控状态")
            return False
        
        # 选择第一个URL进行测试
        test_url = self.successful_urls[0]
        Logger.info(f"使用测试URL检测风控状态: {test_url['url']} (类型: {test_url['type']})")
        
        try:
            # 尝试获取视频列表的第一页
            video_list = await extract_video_list(fetcher, test_url['url'])
            videos = video_list.get("videos", [])
            
            if videos:
                Logger.info("测试URL可以正常获取视频列表，未受到风控")
                return False
            else:
                Logger.warning("测试URL无法获取视频列表，可能受到风控")
                return True
                
        except Exception as e:
            Logger.warning(f"测试URL时出错，可能受到风控: {e}")
            return True
    
    async def check_risk_resolved(self, fetcher: Fetcher) -> bool:
        """检测风控是否已解除"""
        if not self.successful_urls:
            Logger.warning("没有可用的测试URL，无法检测风控解除状态")
            return False
        
        # 选择第一个URL进行测试
        test_url = self.successful_urls[0]
        Logger.info(f"使用测试URL检测风控解除状态: {test_url['url']} (类型: {test_url['type']})")
        
        try:
            # 尝试获取视频列表的第一页
            video_list = await extract_video_list(fetcher, test_url['url'])
            videos = video_list.get("videos", [])
            
            if videos and len(videos) >= 5:  # 至少5个视频才算解除风控
                Logger.info("检测到风控已解除，可以继续获取视频列表")
                self.is_risk_controlled = False
                return True
            else:
                Logger.warning("风控仍未解除，继续等待")
                return False
                
        except Exception as e:
            Logger.warning(f"检测风控解除状态时出错: {e}")
            return False
    
    def set_risk_controlled(self, status: bool) -> None:
        """设置风控状态"""
        self.is_risk_controlled = status
        if status:
            Logger.warning("已设置风控状态为True")
        else:
            Logger.info("已设置风控状态为False")
    
    def get_risk_status(self) -> Dict[str, Any]:
        """获取风控状态信息"""
        return {
            "is_risk_controlled": self.is_risk_controlled,
            "successful_urls_count": len(self.successful_urls),
            "successful_urls": self.successful_urls
        }
    
    def get_test_urls(self) -> List[Dict[str, Any]]:
        """获取测试URL列表"""
        return self.successful_urls.copy()
    
    def clear_test_urls(self) -> None:
        """清空测试URL列表"""
        self.successful_urls.clear()
        Logger.info("已清空测试URL列表")


# 全局风控管理器实例
_anti_risk_manager: Optional[AntiRiskManager] = None


def get_anti_risk_manager() -> AntiRiskManager:
    """获取全局风控管理器实例"""
    global _anti_risk_manager
    if _anti_risk_manager is None:
        _anti_risk_manager = AntiRiskManager()
    return _anti_risk_manager


def reset_anti_risk_manager() -> None:
    """重置全局风控管理器"""
    global _anti_risk_manager
    _anti_risk_manager = None
