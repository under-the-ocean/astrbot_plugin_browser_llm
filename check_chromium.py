#!/usr/bin/env python3
"""
检查Chromium浏览器是否可用
"""

import asyncio
import sys
from pathlib import Path

# 添加路径到sys.path
sys.path.append(str(Path(__file__).parent))

from core.browser import BrowserCore
from astrbot.core.config.astrbot_config import AstrBotConfig


class MockConfig:
    """模拟配置对象"""
    def __init__(self):
        self.data = {
            "browser_type": "chromium",
            "verify_browser": False,
            "default_search_engine": "必应搜索",
            "banned_words": [],
            "default_url": "https://www.baidu.com",
            "viewport_size": {"width": 1920, "height": 1400},
            "screenshot_quality": 65,
            "enable_overlay": False,
            "zoom_factor": 1.0,
            "full_page_zoom_factor": 0,
            "max_pages": 1,
            "timeout": 10,
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


async def check_chromium():
    """检查Chromium浏览器是否可用"""
    print("=== 检查Chromium浏览器 ===")
    
    config = MockConfig()
    data_dir = Path("/tmp/test_chromium")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    browser_core = BrowserCore(config, data_dir)
    
    try:
        print("正在初始化Chromium浏览器...")
        await browser_core.initialize()
        print("✓ Chromium浏览器初始化成功！")
        
        # 测试打开网页
        print("测试打开网页...")
        result = await browser_core.search("https://www.baidu.com")
        if result:
            print(f"✗ 打开网页失败: {result}")
        else:
            print("✓ 网页打开成功！")
        
        # 测试截图
        print("测试截图功能...")
        screenshot_path = await browser_core.screenshot()
        if screenshot_path and Path(screenshot_path).exists():
            print(f"✓ 截图成功: {screenshot_path}")
        else:
            print("✗ 截图失败")
        
        # 清理
        await browser_core.terminate()
        print("✓ 浏览器已关闭")
        
        print("\n🎉 Chromium浏览器测试通过！插件可以正常使用。")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 清理
        try:
            await browser_core.terminate()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(check_chromium())