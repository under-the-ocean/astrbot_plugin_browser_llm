"""
AstrBot LLM 浏览器插件 - 简化版本
基于现有浏览器插件，为每个用户创建持久化缓存文件夹，支持LLM调用
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from astrbot.api import logger
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.register import register_llm_tool
from astrbot.core.provider.register import llm_tools

from core.browser import BrowserCore
from core.favorite import FavoriteManager
from core.operate import BrowserOperator
from core.supervisor import BrowserSupervisor
from core.ticks_overlay import TickOverlay


class UserBrowserInstance:
    """单个用户的浏览器实例"""
    
    def __init__(self, user_id: str, data_dir: Path, config: AstrBotConfig):
        if config is None:
            raise ValueError("config cannot be None")
        self.user_id = user_id
        self.data_dir = data_dir
        self.config = config
        
        # 创建用户专属的缓存目录
        self.cache_dir = data_dir / "screenshot_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建用户专属的收藏夹管理器
        self.favorite_file = data_dir / "user_favorite.json"
        self.fav_mgr = FavoriteManager(self.favorite_file)
        
        # 创建用户专属的刻度叠加器
        self.overlay = TickOverlay(data_dir, data_dir / "resource")
        
        # 创建用户专属的监控器
        self.supervisor = BrowserSupervisor(config.copy(), str(data_dir))
        
        # 创建用户专属的浏览器操作器
        self.operator = BrowserOperator(config, self.fav_mgr, self.overlay, self.supervisor)
        
        # 核心浏览器对象
        self.browser_core = BrowserCore(config, data_dir)
        
        self.initialized = False

    async def initialize(self):
        """初始化用户浏览器实例"""
        if self.initialized:
            return
        
        await self.browser_core.initialize()
        await self.supervisor.start()
        self.initialized = True

    async def terminate(self):
        """终止用户浏览器实例"""
        if not self.initialized:
            return
        
        await self.browser_core.terminate()
        await self.supervisor.stop()
        self.initialized = False

    # ================= 浏览器操作方法 =================
    
    async def search(self, url: str) -> Optional[str]:
        """搜索/访问网页"""
        return await self.browser_core.search(url)

    async def click_coord(self, coords: List[int]) -> Optional[str]:
        """点击坐标"""
        return await self.browser_core.click_coord(coords)

    async def text_input(self, text: str) -> Optional[str]:
        """输入文本"""
        return await self.browser_core.text_input(text)

    async def scroll_by(self, distance: int, direction: str) -> Optional[str]:
        """滚动"""
        return await self.browser_core.scroll_by(distance, direction)

    async def screenshot(self, full_page: bool = False, zoom_factor: Optional[float] = None) -> Optional[str]:
        """截图"""
        return await self.browser_core.screenshot(zoom_factor=zoom_factor, full_page=full_page)

    async def go_back(self) -> Optional[str]:
        """返回上一页"""
        return await self.browser_core.go_back()

    async def go_forward(self) -> Optional[str]:
        """前进到下一页"""
        return await self.browser_core.go_forward()

    async def zoom_to_scale(self, scale: float) -> Optional[str]:
        """缩放"""
        return await self.browser_core.zoom_to_scale(scale)

    async def get_all_tabs_titles(self) -> List[str]:
        """获取所有标签页标题"""
        return await self.browser_core.get_all_tabs_titles()

    async def switch_tab(self, index: int) -> Optional[str]:
        """切换标签页"""
        return await self.browser_core.switch_tab(index)

    async def close_tab(self, index: int) -> str:
        """关闭标签页"""
        return await self.browser_core.close_tab(index)


class UserBrowserManager:
    """用户浏览器实例管理器"""
    
    def __init__(self, base_data_dir: Path, config: AstrBotConfig):
        self.base_data_dir = base_data_dir
        self.config = config
        self.user_browsers: Dict[str, UserBrowserInstance] = {}
        self._lock = asyncio.Lock()

    async def initialize(self):
        """初始化管理器"""
        pass

    async def terminate(self):
        """终止管理器，关闭所有用户浏览器"""
        async with self._lock:
            for browser_instance in self.user_browsers.values():
                try:
                    await browser_instance.terminate()
                except Exception as e:
                    logger.error(f"关闭用户浏览器失败: {e}")
            self.user_browsers.clear()

    async def get_user_browser(self, user_id: str) -> UserBrowserInstance:
        """获取用户的浏览器实例"""
        async with self._lock:
            if user_id not in self.user_browsers:
                # 创建新的用户浏览器实例
                user_data_dir = self.base_data_dir / user_id
                user_data_dir.mkdir(parents=True, exist_ok=True)
                
                browser_instance = UserBrowserInstance(user_id, user_data_dir, self.config)
                await browser_instance.initialize()
                self.user_browsers[user_id] = browser_instance
            
            return self.user_browsers[user_id]

    async def close_user_browser(self, user_id: str):
        """关闭指定用户的浏览器实例"""
        async with self._lock:
            if user_id in self.user_browsers:
                browser_instance = self.user_browsers[user_id]
                await browser_instance.terminate()
                del self.user_browsers[user_id]


class BrowserLLMPlugin(Star):
    """LLM浏览器插件：为每个用户创建独立的浏览器实例，支持持久化缓存"""
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.base_data_dir = StarTools.get_data_dir("astrbot_plugin_browser_llm")
        self.base_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 用户浏览器实例缓存
        self.user_browsers: Dict[str, UserBrowserInstance] = {}
        
        # 资源目录
        self.resource_dir = Path(__file__).resolve().parent / "resource"
        
        # 收藏夹文件（共享）
        self.favorite_file = Path(__file__).parent / "favorite.json"
        self.fav_mgr = FavoriteManager(self.favorite_file)

    async def initialize(self):
        """插件初始化"""
        # 创建用户浏览器实例管理器
        self.browser_manager = UserBrowserManager(self.base_data_dir, self.config)
        await self.browser_manager.initialize()

    async def terminate(self):
        """插件终止，关闭所有用户浏览器实例"""
        await self.browser_manager.terminate()

    # ================= LLM 工具注册 =================
    
    def register_llm_tools(self):
        """注册LLM工具"""
        
        @register_llm_tool(name="browser_open")
        async def browser_open(event: AstrMessageEvent, url: str):
            """
            打开指定网页。
            
            Args:
                url(string): 要访问的网址
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.search(url)
                if result:
                    return f"访问失败: {result}"
                
                # 获取截图
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return f"已打开网页: {url}\n截图已生成"
                else:
                    return f"已打开网页: {url}"
            except Exception as e:
                logger.error(f"browser_open error: {e}")
                return f"打开网页失败: {str(e)}"

        @register_llm_tool(name="browser_click")
        async def browser_click(event: AstrMessageEvent, x: int, y: int):
            """
            在指定坐标点击。
            
            Args:
                x(number): 点击的X坐标
                y(number): 点击的Y坐标
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.click_coord([x, y])
                if result:
                    return f"点击失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return f"已点击坐标({x}, {y})\n截图已更新"
                else:
                    return f"已点击坐标({x}, {y})"
            except Exception as e:
                logger.error(f"browser_click error: {e}")
                return f"点击失败: {str(e)}"

        @register_llm_tool(name="browser_input")
        async def browser_input(event: AstrMessageEvent, text: str):
            """
            在当前页面的输入框中输入文本。
            
            Args:
                text(string): 要输入的文本
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.text_input(text)
                if result:
                    return f"输入失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return f"已输入文本: {text}\n截图已更新"
                else:
                    return f"已输入文本: {text}"
            except Exception as e:
                logger.error(f"browser_input error: {e}")
                return f"输入失败: {str(e)}"

        @register_llm_tool(name="browser_screenshot")
        async def browser_screenshot(event: AstrMessageEvent, full_page: bool = False, zoom_factor: Optional[float] = None):
            """
            获取当前页面的截图。
            
            Args:
                full_page(boolean): 是否截取整页，默认False
                zoom_factor(number): 缩放因子，默认None
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                screenshot_path = await browser_instance.screenshot(full_page=full_page, zoom_factor=zoom_factor)
                if screenshot_path:
                    return f"截图已生成: {screenshot_path}"
                else:
                    return "截图失败"
            except Exception as e:
                logger.error(f"browser_screenshot error: {e}")
                return f"截图失败: {str(e)}"

        @register_llm_tool(name="browser_close")
        async def browser_close(event: AstrMessageEvent):
            """
            关闭当前用户的浏览器实例。
            """
            user_id = str(event.get_sender_id())
            try:
                await self.browser_manager.close_user_browser(user_id)
                return "浏览器已关闭"
            except Exception as e:
                logger.error(f"browser_close error: {e}")
                return f"关闭浏览器失败: {str(e)}"

        @register_llm_tool(name="browser_get_tabs")
        async def browser_get_tabs(event: AstrMessageEvent):
            """
            获取当前用户的标签页列表。
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                titles = await browser_instance.get_all_tabs_titles()
                if titles:
                    return "\n".join(f"{i + 1}. {title}" for i, title in enumerate(titles))
                else:
                    return "暂无打开的标签页"
            except Exception as e:
                logger.error(f"browser_get_tabs error: {e}")
                return f"获取标签页失败: {str(e)}"

        @register_llm_tool(name="browser_back")
        async def browser_back(event: AstrMessageEvent):
            """
            返回上一页。
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.go_back()
                if result:
                    return f"返回失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return "已返回上一页\n截图已更新"
                else:
                    return "已返回上一页"
            except Exception as e:
                logger.error(f"browser_back error: {e}")
                return f"返回失败: {str(e)}"

        @register_llm_tool(name="browser_forward")
        async def browser_forward(event: AstrMessageEvent):
            """
            前往下一页。
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.go_forward()
                if result:
                    return f"前进失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return "已前往下一页\n截图已更新"
                else:
                    return "已前往下一页"
            except Exception as e:
                logger.error(f"browser_forward error: {e}")
                return f"前进失败: {str(e)}"

        @register_llm_tool(name="browser_zoom")
        async def browser_zoom(event: AstrMessageEvent, scale: float = 1.5):
            """
            缩放页面。
            
            Args:
                scale(number): 缩放因子，默认1.5
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.zoom_to_scale(scale)
                if result:
                    return f"缩放失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return f"已缩放到 {scale} 倍\n截图已更新"
                else:
                    return f"已缩放到 {scale} 倍"
            except Exception as e:
                logger.error(f"browser_zoom error: {e}")
                return f"缩放失败: {str(e)}"

        @register_llm_tool(name="browser_scroll")
        async def browser_scroll(event: AstrMessageEvent, direction: str = "下", distance: int = 1300):
            """
            滚动网页。
            
            Args:
                direction(string): 滚动方向，可选"上"、"下"、"左"、"右"
                distance(number): 滚动距离，默认1300像素
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.scroll_by(distance, direction)
                if result:
                    return f"滚动失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return f"已{direction}滚动{distance}像素\n截图已更新"
                else:
                    return f"已{direction}滚动{distance}像素"
            except Exception as e:
                logger.error(f"browser_scroll error: {e}")
                return f"滚动失败: {str(e)}"

        @register_llm_tool(name="browser_switch_tab")
        async def browser_switch_tab(event: AstrMessageEvent, index: int):
            """
            切换到指定标签页。
            
            Args:
                index(number): 标签页序号（从1开始）
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.switch_tab(index - 1)
                if result:
                    return f"切换标签页失败: {result}"
                
                screenshot_path = await browser_instance.screenshot()
                if screenshot_path:
                    return f"已切换到标签页 {index}\n截图已更新"
                else:
                    return f"已切换到标签页 {index}"
            except Exception as e:
                logger.error(f"browser_switch_tab error: {e}")
                return f"切换标签页失败: {str(e)}"

        @register_llm_tool(name="browser_close_tab")
        async def browser_close_tab(event: AstrMessageEvent, index: int):
            """
            关闭指定标签页。
            
            Args:
                index(number): 标签页序号（从1开始）
            """
            user_id = str(event.get_sender_id())
            try:
                browser_instance = await self.browser_manager.get_user_browser(user_id)
                result = await browser_instance.close_tab(index - 1)
                if result:
                    return f"关闭标签页失败: {result}"
                else:
                    return f"已关闭标签页 {index}"
            except Exception as e:
                logger.error(f"browser_close_tab error: {e}")
                return f"关闭标签页失败: {str(e)}"