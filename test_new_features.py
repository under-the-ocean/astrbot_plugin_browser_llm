#!/usr/bin/env python3
"""
测试新增的浏览器功能
"""

import asyncio
import json
from pathlib import Path
from astrbot.core.config.astrbot_config import AstrBotConfig

async def test_new_features():
    """测试新增的浏览器功能"""
    
    # 创建测试配置
    config = AstrBotConfig()
    config["browser_type"] = "chromium"
    config["timeout"] = 30
    config["screenshot_quality"] = 80
    config["headless"] = True
    config["viewport_size"] = {"width": 1280, "height": 720}
    config["default_url"] = "https://www.baidu.com"
    config["max_pages"] = 5
    config["zoom_factor"] = 1.0
    
    # 导入必要的模块
    from browser_llm_plugin import UserBrowserInstance, UserBrowserManager
    
    print("🧪 开始测试新增的浏览器功能...")
    
    # 创建临时数据目录
    test_data_dir = Path("/tmp/browser_test")
    test_data_dir.mkdir(exist_ok=True)
    
    try:
        # 创建用户浏览器实例
        user_instance = UserBrowserInstance("test_user", test_data_dir, config)
        await user_instance.initialize()
        
        print("✅ 用户浏览器实例创建成功")
        
        # 测试 1: 打开网页
        print("\n📍 测试 1: 打开网页")
        result = await user_instance.search("https://www.baidu.com")
        if result:
            print(f"❌ 打开网页失败: {result}")
        else:
            print("✅ 打开网页成功")
        
        # 测试 2: 获取页面源码
        print("\n📍 测试 2: 获取页面源码")
        source = await user_instance.get_page_source()
        if source:
            print(f"✅ 获取页面源码成功，长度: {len(source)} 字符")
            print(f"🔍 前 200 字符预览: {source[:200]}...")
        else:
            print("❌ 获取页面源码失败")
        
        # 测试 3: 查找元素
        print("\n📍 测试 3: 查找元素")
        elements = await user_instance.find_elements("input", "css", "name")
        if isinstance(elements, list):
            print(f"✅ 查找元素成功，找到 {len(elements)} 个元素")
            if elements:
                print(f"🔍 第一个元素: {elements[0]}")
        else:
            print(f"❌ 查找元素失败: {elements}")
        
        # 测试 4: 获取元素文本
        print("\n📍 测试 4: 获取元素文本")
        text = await user_instance.get_element_text("#su")
        if text:
            print(f"✅ 获取元素文本成功: {text[:50]}...")
        else:
            print("❌ 获取元素文本失败")
        
        # 测试 5: 获取元素属性
        print("\n📍 测试 5: 获取元素属性")
        attr = await user_instance.get_element_attribute("#su", "id")
        if attr:
            print(f"✅ 获取元素属性成功: {attr}")
        else:
            print("❌ 获取元素属性失败")
        
        # 测试 6: 等待元素
        print("\n📍 测试 6: 等待元素")
        result = await user_instance.wait_for_element("#su", 5, "css")
        if not result:
            print("✅ 等待元素成功")
        else:
            print(f"❌ 等待元素失败: {result}")
        
        # 测试 7: 通过选择器输入文本
        print("\n📍 测试 7: 通过选择器输入文本")
        result = await user_instance.text_input_by_selector("#su", "测试文本", "css")
        if not result:
            print("✅ 通过选择器输入文本成功")
        else:
            print(f"❌ 通过选择器输入文本失败: {result}")
        
        # 测试 8: 通过选择器点击元素
        print("\n📍 测试 8: 通过选择器点击元素")
        result = await user_instance.click_element("#su", "css")
        if not result:
            print("✅ 通过选择器点击元素成功")
        else:
            print(f"❌ 通过选择器点击元素失败: {result}")
        
        print("\n🎉 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        try:
            await user_instance.terminate()
            print("✅ 资源清理完成")
        except Exception as e:
            print(f"⚠️ 资源清理时出现错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_new_features())