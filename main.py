"""
AstrBot LLM 浏览器插件 - 主入口文件
基于现有浏览器插件，为每个用户创建持久化缓存文件夹，支持LLM调用
"""

from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig

from .browser_llm_plugin import BrowserLLMPlugin


class BrowserLLMPluginStar(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        if config is None:
            from astrbot.core.config.astrbot_config import AstrBotConfig
            config = AstrBotConfig()
        self.config = config
        # 数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_browser_llm")
        
        # 将 AstrBot 配置转换为插件格式
        self.plugin_config = self._convert_config(config)

    def _convert_config(self, config: AstrBotConfig) -> dict:
        """将 AstrBot 配置转换为插件配置格式"""
        plugin_config = {
            "browser_type": config.get("browser_type", "chromium"),
            "verify_browser": config.get("verify_browser", True),
            "default_search_engine": config.get("default_search_engine", "必应搜索"),
            "banned_words": config.get("banned_words", []),
            "default_url": config.get("default_url", "https://www.baidu.com"),
            "viewport_size": {
                "width": config.get("viewport_width", 1920),
                "height": config.get("viewport_height", 1400)
            },
            "screenshot_quality": config.get("screenshot_quality", 65),
            "enable_overlay": config.get("enable_overlay", True),
            "zoom_factor": config.get("zoom_factor", 1.5),
            "full_page_zoom_factor": config.get("full_page_zoom_factor", 0),
            "max_pages": config.get("max_pages", 5),
            "timeout": config.get("timeout", 30),
            "headless": config.get("headless", True),
            "supervisor": {
                "max_memory_percent": config.get("max_memory_percent", 80),
                "max_process_memory_mb": config.get("max_process_memory_mb", 512),
                "idle_timeout": config.get("idle_timeout", 600),
                "monitor_interval": config.get("monitor_interval", 10),
                "cache_max_size_mb": config.get("cache_max_size_mb", 200),
                "cache_max_age_hours": config.get("cache_max_age_hours", 2),
                "screenshot_max_bytes": config.get("screenshot_max_bytes", 5242880),
                "max_concurrent_users": config.get("max_concurrent_users", 10),
                "global_browser_count_limit": config.get("global_browser_count_limit", 20),
                "max_operations_per_minute": config.get("max_operations_per_minute", 20),
                "hard_operation_timeout": config.get("hard_operation_timeout", 60)
            }
        }
        return plugin_config

    # ================= 生命周期 ===================

    async def initialize(self):
        """插件加载时触发"""
        # 创建LLM插件实例
        self.llm_plugin = BrowserLLMPlugin(self.context, self.plugin_config)
        await self.llm_plugin.initialize()
        
        # 注册LLM工具
        self.llm_plugin.register_llm_tools()

    async def terminate(self):
        """插件卸载时触发"""
        if hasattr(self, 'llm_plugin'):
            await self.llm_plugin.terminate()

    # ================= 传统命令接口（可选） ===================

    @filter.command("浏览器LLM安装")
    async def install_browser_llm(self, event):
        """安装浏览器依赖"""
        from .core.downloader import BrowserDownloader
        downloader = BrowserDownloader(self.data_dir)
        yield event.plain_result("正在安装浏览器依赖...")
        ok, msg = await downloader.download(self.config["browser_type"])
        yield event.plain_result(msg)

    @filter.command("浏览器LLM截图")
    async def browser_llm_screenshot(self, event):
        """获取当前用户的浏览器截图"""
        user_id = str(event.get_sender_id())
        try:
            screenshot_path = await self.llm_plugin.browser_manager.get_user_browser(user_id).screenshot()
            if screenshot_path:
                yield event.image_result(Path(screenshot_path))
            else:
                yield event.plain_result("截图失败")
        except Exception as e:
            yield event.plain_result(f"截图失败: {str(e)}")

    @filter.command("浏览器LLM状态")
    async def browser_llm_status(self, event):
        """查看浏览器状态"""
        user_id = str(event.get_sender_id())
        try:
            browser_instance = await self.llm_plugin.browser_manager.get_user_browser(user_id)
            titles = await browser_instance.get_all_tabs_titles()
            if titles:
                status_text = "\n".join(f"{i + 1}. {title}" for i, title in enumerate(titles))
            else:
                status_text = "暂无打开的标签页"
            
            yield event.plain_result(f"用户 {user_id} 的浏览器状态:\n{status_text}")
        except Exception as e:
            yield event.plain_result(f"获取状态失败: {str(e)}")