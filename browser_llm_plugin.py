"""
AstrBot LLM 浏览器插件 — 增强资源管控版
基于现有浏览器插件，为每个用户创建持久化缓存文件夹，支持LLM调用
绕过系统对AI执行命令的30秒限制

新增资源限制:
1. 全局最大并发用户数
2. 全局活跃浏览器总数上限
3. 定期清理过期用户浏览器
4. 操作频率限制
5. Supervisor 进程级内存监控
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from astrbot.api import logger
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.register import register_llm_tool

from core.browser import BrowserCore
from core.favorite import FavoriteManager
from core.operate import BrowserOperator
from core.supervisor import BrowserSupervisor
from core.ticks_overlay import TickOverlay


class UserBrowserManager:
    """用户浏览器实例管理器 — 增强资源管控版"""

    def __init__(self, base_data_dir: Path, config: dict):
        self.base_data_dir = base_data_dir
        self.config = config

        # 用户浏览器实例池
        self.user_browsers: Dict[str, UserBrowserInstance] = {}
        self._lock = asyncio.Lock()

        # ===== 全局资源限制 =====
        sup_cfg = config.get("supervisor", {})
        self.max_concurrent_users: int = sup_cfg.get("max_concurrent_users", 10)
        self.global_browser_count_limit: int = sup_cfg.get("global_browser_count_limit", 20)

        # ===== 清理任务 =====
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval: int = sup_cfg.get("idle_timeout", 600) // 2  # 闲置超时的一半

    async def initialize(self):
        """启动定期清理任务"""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup_loop())

    async def terminate(self):
        """终止管理器，关闭所有浏览器"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        async with self._lock:
            for browser_instance in self.user_browsers.values():
                try:
                    await browser_instance.terminate()
                except Exception as e:
                    logger.error(f"关闭用户浏览器失败: {e}")
            self.user_browsers.clear()
            logger.info(f"[资源管理] 已关闭全部 {len(self.user_browsers)} 个用户浏览器实例")

    async def get_user_browser(self, user_id: str, event: Optional[AstrMessageEvent] = None) -> UserBrowserInstance:
        """获取用户的浏览器实例，带全局并发限制"""
        async with self._lock:
            # ===== 已存在则直接返回 =====
            if user_id in self.user_browsers:
                return self.user_browsers[user_id]

            # ===== 全局并发用户数检查 =====
            if len(self.user_browsers) >= self.max_concurrent_users:
                # 尝试清理最不活跃的浏览器
                await self._evict_least_active()
                # 如果还是满了，拒绝
                if len(self.user_browsers) >= self.max_concurrent_users:
                    raise RuntimeError(
                        f"服务器忙碌中，当前活跃用户数已达上限"
                        f"({self.max_concurrent_users}人)，请稍后再试"
                    )

            # ===== 全局浏览器总数检查 =====
            if len(self.user_browsers) >= self.global_browser_count_limit:
                await self._evict_least_active()

            # ===== 创建新实例 =====
            user_data_dir = self.base_data_dir / user_id
            user_data_dir.mkdir(parents=True, exist_ok=True)

            browser_instance = UserBrowserInstance(user_id, user_data_dir, self.config)
            await browser_instance.initialize()
            self.user_browsers[user_id] = browser_instance

            logger.info(
                f"[资源管理] 为用户 {user_id} 创建浏览器实例, "
                f"当前活跃: {len(self.user_browsers)}/{self.max_concurrent_users}"
            )

            return self.user_browsers[user_id]

    async def close_user_browser(self, user_id: str):
        """关闭指定用户的浏览器实例"""
        async with self._lock:
            if user_id in self.user_browsers:
                browser_instance = self.user_browsers[user_id]
                await browser_instance.terminate()
                del self.user_browsers[user_id]
                logger.info(
                    f"[资源管理] 已关闭用户 {user_id} 的浏览器, "
                    f"当前活跃: {len(self.user_browsers)}"
                )

    async def _evict_least_active(self):
        """驱逐最不活跃的浏览器（创建时间最早）"""
        if not self.user_browsers:
            return

        # 按创建时间排序（粗略用 user_id 稳定性排序）
        sorted_users = sorted(
            self.user_browsers.items(),
            key=lambda x: x[1].created_at
        )
        victim_id, victim_instance = sorted_users[0]
        try:
            await victim_instance.terminate()
            del self.user_browsers[victim_id]
            logger.warning(
                f"[资源管理] 驱逐用户 {victim_id} 的浏览器 (资源上限)"
            )
        except Exception as e:
            logger.error(f"[资源管理] 驱逐失败: {e}")

    async def _periodic_cleanup_loop(self):
        """定期清理空闲过期的浏览器"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                async with self._lock:
                    stale_ids = []
                    for uid, instance in self.user_browsers.items():
                        if instance.is_stale(self._cleanup_interval * 2):
                            stale_ids.append(uid)

                    for uid in stale_ids:
                        try:
                            await self.user_browsers[uid].terminate()
                            del self.user_browsers[uid]
                            logger.info(
                                f"[资源管理] 自动清理用户 {uid} 的过期浏览器"
                            )
                        except Exception as e:
                            logger.error(f"[资源管理] 清理失败: {e}")

                    if stale_ids:
                        logger.info(
                            f"[资源管理] 清理了 {len(stale_ids)} 个过期浏览器, "
                            f"当前活跃: {len(self.user_browsers)}"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[资源管理] 清理循环异常: {e}")

    def get_status(self) -> dict:
        """获取管理器状态"""
        return {
            "active_users": len(self.user_browsers),
            "max_concurrent_users": self.max_concurrent_users,
            "global_browser_count_limit": self.global_browser_count_limit,
            "users": list(self.user_browsers.keys()),
        }


class UserBrowserInstance:
    """单个用户的浏览器实例 — 增强版"""

    def __init__(self, user_id: str, data_dir: Path, config: dict):
        if config is None:
            raise ValueError("config cannot be None")
        self.user_id = user_id
        self.data_dir = data_dir
        self.config = config
        self.created_at = time.time()
        self._last_used = time.time()

        # 用户专属缓存目录
        self.cache_dir = data_dir / "screenshot_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 用户专属收藏夹管理器
        self.favorite_file = data_dir / "user_favorite.json"
        self.fav_mgr = FavoriteManager(self.favorite_file)

        # 用户专属刻度叠加器
        self.overlay = TickOverlay(data_dir, data_dir / "resource")

        # 用户专属监控器（增强版）
        self.supervisor = BrowserSupervisor(config.copy(), str(data_dir))

        # 用户专属浏览器操作器
        self.operator = BrowserOperator(config, self.fav_mgr, self.overlay, self.supervisor)

        # 核心浏览器对象
        self.browser_core = BrowserCore(config, data_dir)

        self.initialized = False

    @property
    def idle_seconds(self) -> float:
        """获取闲置秒数"""
        return time.time() - self._last_used

    def is_stale(self, max_idle: float = 600) -> bool:
        """判断是否过期（闲置超过阈值）"""
        return self.idle_seconds > max_idle

    def touch(self):
        """更新最后使用时间"""
        self._last_used = time.time()

    async def initialize(self):
        """初始化"""
        if self.initialized:
            return
        await self.browser_core.initialize()
        await self.supervisor.start()
        self.initialized = True
        self.touch()

    async def terminate(self):
        """终止"""
        if not self.initialized:
            return
        await self.browser_core.terminate()
        await self.supervisor.stop()
        self.initialized = False

    # ================= 浏览器操作方法（带 touch） =================

    async def search(self, url: str) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("search", url=url)

    async def click_coord(self, coords: List[int]) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("click_coord", coords=coords)

    async def text_input(self, text: str) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("text_input", text=text)

    async def scroll_by(self, distance: int, direction: str) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("scroll_by", distance=distance, direction=direction)

    async def screenshot(self, full_page: bool = False, zoom_factor: Optional[float] = None) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("screenshot", zoom_factor=zoom_factor, full_page=full_page)

    async def go_back(self) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("go_back")

    async def go_forward(self) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("go_forward")

    async def zoom_to_scale(self, scale: float) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("zoom_to_scale", scale=scale)

    async def get_all_tabs_titles(self) -> List[str]:
        self.touch()
        return await self.supervisor.call("get_all_tabs_titles")

    async def switch_tab(self, index: int) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("switch_tab", index=index)

    async def close_tab(self, index: int) -> str:
        self.touch()
        return await self.supervisor.call("close_tab", index=index)

    # ================= 新功能 =================

    async def get_page_source(self) -> Optional[str]:
        self.touch()
        return await self.supervisor.call("get_page_source")

    async def click_element(self, selector: str, selector_type: str = "css") -> Optional[str]:
        self.touch()
        return await self.supervisor.call("click_element", selector=selector, selector_type=selector_type)

    async def text_input_by_selector(self, selector: str, text: str, selector_type: str = "css") -> Optional[str]:
        self.touch()
        return await self.supervisor.call("text_input_by_selector", selector=selector, text=text, selector_type=selector_type)

    async def find_elements(self, selector: str, selector_type: str = "css", attribute: Optional[str] = None) -> Any:
        self.touch()
        return await self.supervisor.call("find_elements", selector=selector, selector_type=selector_type, attribute=attribute)

    async def get_element_text(self, selector: str, selector_type: str = "css") -> Optional[str]:
        self.touch()
        return await self.supervisor.call("get_element_text", selector=selector, selector_type=selector_type)

    async def get_element_attribute(self, selector: str, attribute_name: str, selector_type: str = "css") -> Optional[str]:
        self.touch()
        return await self.supervisor.call("get_element_attribute", selector=selector, attribute_name=attribute_name, selector_type=selector_type)

    async def wait_for_element(self, selector: str, timeout: float = 30, selector_type: str = "css") -> Optional[str]:
        self.touch()
        return await self.supervisor.call("wait_for_element", selector=selector, timeout=timeout, selector_type=selector_type)


class BrowserLLMPlugin(Star):
    """LLM浏览器插件：增强资源管控版"""

    def __init__(self, context: Context, config: dict):
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
        self.browser_manager = UserBrowserManager(self.base_data_dir, self.config)
        await self.browser_manager.initialize()

    async def terminate(self):
        """插件终止"""
        await self.browser_manager.terminate()

    # ================= 通用工具方法 =================

    async def _get_browser_instance(self, event: AstrMessageEvent) -> UserBrowserInstance:
        """获取用户浏览器实例（带资源检查和统一异常处理）"""
        user_id = str(event.get_sender_id())
        try:
            return await self.browser_manager.get_user_browser(user_id, event)
        except RuntimeError as e:
            raise  # 资源限制错误直接透传
        except Exception as e:
            logger.error(f"获取用户浏览器实例失败: {e}")
            raise RuntimeError(f"浏览器初始化失败: {str(e)}")

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
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.search(url)
                if result:
                    return f"访问失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已打开网页: {url}\n截图已生成"
                return f"已打开网页: {url}"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"打开网页失败: {str(e)}"

        @register_llm_tool(name="browser_click")
        async def browser_click(event: AstrMessageEvent, x: int, y: int):
            """
            在指定坐标点击。

            Args:
                x(number): 点击的X坐标
                y(number): 点击的Y坐标
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.click_coord([x, y])
                if result:
                    return f"点击失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已点击坐标({x}, {y})\n截图已更新"
                return f"已点击坐标({x}, {y})"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"点击失败: {str(e)}"

        @register_llm_tool(name="browser_input")
        async def browser_input(event: AstrMessageEvent, text: str):
            """
            在当前页面的输入框中输入文本。

            Args:
                text(string): 要输入的文本
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.text_input(text)
                if result:
                    return f"输入失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已输入文本: {text}\n截图已更新"
                return f"已输入文本: {text}"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"输入失败: {str(e)}"

        @register_llm_tool(name="browser_scroll")
        async def browser_scroll(event: AstrMessageEvent, direction: str = "下", distance: int = 1300):
            """
            滚动网页。

            Args:
                direction(string): 滚动方向，可选"上"、"下"、"左"、"右"
                distance(number): 滚动距离，默认1300像素
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.scroll_by(distance, direction)
                if result:
                    return f"滚动失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已{direction}滚动{distance}像素\n截图已更新"
                return f"已{direction}滚动{distance}像素"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"滚动失败: {str(e)}"

        @register_llm_tool(name="browser_screenshot")
        async def browser_screenshot(event: AstrMessageEvent, full_page: bool = False, zoom_factor: Optional[float] = None):
            """
            获取当前页面的截图。

            Args:
                full_page(boolean): 是否截取整页，默认False
                zoom_factor(number): 缩放因子，默认None
            """
            try:
                browser = await self._get_browser_instance(event)
                screenshot_path = await browser.screenshot(full_page=full_page, zoom_factor=zoom_factor)
                if screenshot_path:
                    return f"截图已生成: {screenshot_path}"
                return "截图失败"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"截图失败: {str(e)}"

        @register_llm_tool(name="browser_get_source")
        async def browser_get_source(event: AstrMessageEvent, save_to_file: bool = False):
            """
            获取当前页面的 HTML 源代码。

            Args:
                save_to_file(boolean): 是否保存到文件，默认False。设为True时返回文件路径
            """
            try:
                browser = await self._get_browser_instance(event)
                source = await browser.get_page_source()
                if not source:
                    return "获取页面源码失败"

                if save_to_file:
                    source_file = browser.data_dir / f"page_source_{int(time.time())}.html"
                    source_file.write_text(source, encoding='utf-8')
                    return f"页面源码已保存到: {source_file}"
                else:
                    if len(source) > 5000:
                        preview = source[:5000]
                        return (f"页面源码过长，返回前5000字符：\n{preview}"
                                f"\n...（共{len(source)}字符，如需完整内容请设 save_to_file=True）")
                    return f"页面源码：\n{source}"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"获取页面源码失败: {str(e)}"

        @register_llm_tool(name="browser_click_element")
        async def browser_click_element(event: AstrMessageEvent, selector: str, selector_type: str = "css"):
            """
            通过选择器点击元素。

            Args:
                selector(string): 选择器表达式，如 "#submit-btn"、".btn-primary"、'//button[contains(text(), "登录")]'
                selector_type(string): 选择器类型，"css" 或 "xpath"，默认 "css"
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.click_element(selector, selector_type)
                if result:
                    return f"点击元素失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已点击元素(选择器: {selector})\n截图已更新"
                return f"已点击元素(选择器: {selector})"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"点击元素失败: {str(e)}"

        @register_llm_tool(name="browser_input_by_selector")
        async def browser_input_by_selector(event: AstrMessageEvent, selector: str, text: str, selector_type: str = "css"):
            """
            通过选择器在输入框中输入文本。

            Args:
                selector(string): 选择器表达式
                text(string): 要输入的文本
                selector_type(string): 选择器类型，"css" 或 "xpath"，默认 "css"
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.text_input_by_selector(selector, text, selector_type)
                if result:
                    return f"输入失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已通过选择器输入文本: {text}\n截图已更新"
                return f"已通过选择器输入文本: {text}"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"输入失败: {str(e)}"

        @register_llm_tool(name="browser_find_elements")
        async def browser_find_elements(event: AstrMessageEvent, selector: str, selector_type: str = "css", attribute: Optional[str] = None):
            """
            查找页面元素并返回其信息。

            Args:
                selector(string): 选择器表达式
                selector_type(string): 选择器类型，"css" 或 "xpath"，默认 "css"
                attribute(string): 可选，指定要获取的属性名，如 "href"、"src"、"innerText"
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.find_elements(selector, selector_type, attribute)
                if isinstance(result, str):
                    return result

                lines = [f"找到 {len(result)} 个元素:"]
                for i, item in enumerate(result):
                    parts = []
                    parts.append(f"[{i + 1}] <{item.get('tag', '?')}>")
                    if item.get('text'):
                        parts.append(f"文本: {item['text'][:100]}")
                    if attribute and item.get(attribute):
                        parts.append(f"{attribute}: {item[attribute]}")
                    lines.append("  ".join(parts))

                return "\n".join(lines)
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"查找元素失败: {str(e)}"

        @register_llm_tool(name="browser_get_element_text")
        async def browser_get_element_text(event: AstrMessageEvent, selector: str, selector_type: str = "css"):
            """
            获取元素的文本内容。

            Args:
                selector(string): 选择器表达式
                selector_type(string): 选择器类型，"css" 或 "xpath"，默认 "css"
            """
            try:
                browser = await self._get_browser_instance(event)
                text = await browser.get_element_text(selector, selector_type)
                if text:
                    return f"元素文本内容: {text[:1000]}"
                return "未找到指定元素或元素无文本内容"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"获取元素文本失败: {str(e)}"

        @register_llm_tool(name="browser_get_element_attribute")
        async def browser_get_element_attribute(event: AstrMessageEvent, selector: str, attribute_name: str, selector_type: str = "css"):
            """
            获取元素的指定属性值。

            Args:
                selector(string): 选择器表达式
                attribute_name(string): 属性名，如 "href"、"src"、"class"、"id"、"alt"
                selector_type(string): 选择器类型，"css" 或 "xpath"，默认 "css"
            """
            try:
                browser = await self._get_browser_instance(event)
                value = await browser.get_element_attribute(selector, attribute_name, selector_type)
                if value is not None:
                    return f"元素属性 [{attribute_name}] = {value}"
                return "未找到指定元素或属性不存在"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"获取元素属性失败: {str(e)}"

        @register_llm_tool(name="browser_wait_for_element")
        async def browser_wait_for_element(event: AstrMessageEvent, selector: str, timeout: float = 30, selector_type: str = "css"):
            """
            等待元素出现。

            Args:
                selector(string): 选择器表达式
                timeout(number): 超时时间（秒），默认30秒
                selector_type(string): 选择器类型，"css" 或 "xpath"，默认 "css"
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.wait_for_element(selector, timeout, selector_type)
                if result:
                    return f"等待元素失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"元素已出现(选择器: {selector})\n截图已更新"
                return f"元素已出现(选择器: {selector})"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"等待元素失败: {str(e)}"

        @register_llm_tool(name="browser_back")
        async def browser_back(event: AstrMessageEvent):
            """
            返回上一页。
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.go_back()
                if result:
                    return f"返回失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return "已返回上一页\n截图已更新"
                return "已返回上一页"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"返回失败: {str(e)}"

        @register_llm_tool(name="browser_forward")
        async def browser_forward(event: AstrMessageEvent):
            """
            前往下一页。
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.go_forward()
                if result:
                    return f"前进失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return "已前往下一页\n截图已更新"
                return "已前往下一页"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"前进失败: {str(e)}"

        @register_llm_tool(name="browser_zoom")
        async def browser_zoom(event: AstrMessageEvent, scale: float = 1.5):
            """
            缩放页面。

            Args:
                scale(number): 缩放因子，默认1.5
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.zoom_to_scale(scale)
                if result:
                    return f"缩放失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已缩放到 {scale} 倍\n截图已更新"
                return f"已缩放到 {scale} 倍"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"缩放失败: {str(e)}"

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
                return f"关闭浏览器失败: {str(e)}"

        @register_llm_tool(name="browser_get_tabs")
        async def browser_get_tabs(event: AstrMessageEvent):
            """
            获取当前用户的标签页列表。
            """
            try:
                browser = await self._get_browser_instance(event)
                titles = await browser.get_all_tabs_titles()
                if titles:
                    return "\n".join(f"{i + 1}. {title}" for i, title in enumerate(titles))
                return "暂无打开的标签页"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"获取标签页失败: {str(e)}"

        @register_llm_tool(name="browser_switch_tab")
        async def browser_switch_tab(event: AstrMessageEvent, index: int):
            """
            切换到指定标签页。

            Args:
                index(number): 标签页序号（从1开始）
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.switch_tab(index - 1)
                if result:
                    return f"切换标签页失败: {result}"
                screenshot_path = await browser.screenshot()
                if screenshot_path:
                    return f"已切换到标签页 {index}\n截图已更新"
                return f"已切换到标签页 {index}"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"切换标签页失败: {str(e)}"

        @register_llm_tool(name="browser_close_tab")
        async def browser_close_tab(event: AstrMessageEvent, index: int):
            """
            关闭指定标签页。

            Args:
                index(number): 标签页序号（从1开始）
            """
            try:
                browser = await self._get_browser_instance(event)
                result = await browser.close_tab(index - 1)
                if result:
                    return f"关闭标签页失败: {result}"
                return f"已关闭标签页 {index}"
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"关闭标签页失败: {str(e)}"
