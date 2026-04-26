#!/usr/bin/env python3
"""
B站登录截图脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from browser_llm_plugin_simple import BrowserLLMPlugin
from astrbot.core.config.astrbot_config import AstrBotConfig


class MockContext:
    """模拟Context对象"""
    pass


class MockConfig:
    """模拟配置对象"""
    def __init__(self):
        self.data = {
            "browser_type": "chromium",
            "verify_browser": False,
            "default_search_engine": "必应搜索",
            "banned_words": [],
            "default_url": "https://www.bilibili.com",
            "viewport_size": {"width": 1920, "height": 1400},
            "screenshot_quality": 80,
            "enable_overlay": False,
            "zoom_factor": 1.0,
            "full_page_zoom_factor": 0,
            "max_pages": 3,
            "timeout": 15,
            "supervisor": {
                "max_memory_percent": 90,
                "idle_timeout": 600,
                "monitor_interval": 10.0
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


async def get_bilibili_login_qr():
    """获取B站登录二维码"""
    print("=== 获取B站登录二维码 ===")
    
    context = MockContext()
    config = MockConfig()
    
    plugin = BrowserLLMPlugin(context, config)
    
    try:
        # 初始化插件
        await plugin.initialize()
        print("✓ 插件初始化成功")
        
        # 获取用户浏览器实例
        user_id = "bilibili_login_user"
        browser_instance = await plugin.browser_manager.get_user_browser(user_id)
        print(f"✓ 获取用户浏览器实例: {user_id}")
        
        # 访问B站登录页面
        print("正在访问B站登录页面...")
        result = await browser_instance.search("https://passport.bilibili.com/login")
        if result:
            print(f"✗ 访问失败: {result}")
            return None
        
        # 等待页面加载
        print("等待页面加载...")
        await asyncio.sleep(3)
        
        # 截图
        print("正在截图...")
        screenshot_path = await browser_instance.screenshot()
        print(f"截图路径: {screenshot_path}")
        
        if screenshot_path and Path(screenshot_path).exists():
            print(f"✓ 截图成功! 文件大小: {Path(screenshot_path).stat().st_size} bytes")
            return screenshot_path
        else:
            print("✗ 截图失败")
            return None
            
    except Exception as e:
        print(f"✗ 操作失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        # 关闭浏览器
        try:
            await browser_instance.terminate()
            print("✓ 浏览器已关闭")
        except:
            pass
        
        # 终止插件
        try:
            await plugin.terminate()
            print("✓ 插件已终止")
        except:
            pass


if __name__ == "__main__":
    result = asyncio.run(get_bilibili_login_qr())
    print(f"\n最终结果: {result}")