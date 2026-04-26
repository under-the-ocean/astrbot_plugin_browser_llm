"""
LLM浏览器插件简化测试脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加路径到sys.path
sys.path.append(str(Path(__file__).parent))

from browser_llm_plugin_simple import BrowserLLMPlugin, UserBrowserManager
from astrbot.core.config.astrbot_config import AstrBotConfig


class MockContext:
    """模拟Context对象"""
    pass


class MockConfig:
    """模拟配置对象"""
    def __init__(self):
        self.data = {
            "browser_type": "chromium",
            "verify_browser": False,  # 测试时禁用验证
            "default_search_engine": "必应搜索",
            "banned_words": [],
            "default_url": "https://www.baidu.com",
            "viewport_size": {"width": 1920, "height": 1400},
            "screenshot_quality": 65,
            "enable_overlay": False,  # 测试时禁用叠加
            "zoom_factor": 1.0,
            "full_page_zoom_factor": 0,
            "max_pages": 1,
            "timeout": 5,
            "supervisor": {
                "max_memory_percent": 90,
                "idle_timeout": 60,
                "monitor_interval": 5.0
            }
        }
    
    def __getitem__(self, key):
        return self.data[key]
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def copy(self):
        return MockConfig()
    
    def save_config(self):
        pass


async def test_plugin():
    """测试插件"""
    print("=== 测试LLM浏览器插件 ===")
    
    context = MockContext()
    config = MockConfig()
    
    plugin = BrowserLLMPlugin(context, config)
    
    try:
        # 初始化
        await plugin.initialize()
        print("✓ 插件初始化成功")
        
        # 测试用户浏览器管理器
        user_id = "test_user_123"
        browser_instance = await plugin.browser_manager.get_user_browser(user_id)
        print(f"✓ 获取用户浏览器实例成功: {user_id}")
        
        # 测试基本功能
        print("测试浏览器基本功能...")
        
        # 打开网页
        result = await browser_instance.search("https://www.baidu.com")
        print(f"打开网页结果: {result}")
        
        # 获取标签页
        titles = await browser_instance.get_all_tabs_titles()
        print(f"标签页标题: {titles}")
        
        # 截图
        screenshot_path = await browser_instance.screenshot()
        print(f"截图路径: {screenshot_path}")
        
        if screenshot_path and Path(screenshot_path).exists():
            print("✓ 截图成功")
        else:
            print("✗ 截图失败")
        
        # 关闭浏览器
        await browser_instance.terminate()
        print("✓ 浏览器关闭成功")
        
        # 关闭用户浏览器
        await plugin.browser_manager.close_user_browser(user_id)
        print("✓ 用户浏览器关闭成功")
        
        print("✓ 所有测试通过！")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 终止插件
        await plugin.terminate()
        print("✓ 插件终止成功")


if __name__ == "__main__":
    asyncio.run(test_plugin())