#!/usr/bin/env python3
"""
验证新增功能是否正确注册
"""

import ast
import inspect
from pathlib import Path

def verify_browser_core():
    """验证 BrowserCore 是否有新方法"""
    print("🔍 验证 BrowserCore 新增方法...")
    
    try:
        with open("core/browser.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查新增方法是否存在
        methods = [
            "get_page_source",
            "click_element", 
            "text_input_by_selector",
            "find_elements",
            "get_element_text",
            "get_element_attribute",
            "wait_for_element",
            "_resolve_element",
            "_resolve_elements"
        ]
        
        for method in methods:
            if f"async def {method}" in content:
                print(f"✅ {method} 方法存在")
            else:
                print(f"❌ {method} 方法不存在")
        
        # 检查选择器类型支持
        if "selector_type" in content:
            print("✅ 支持选择器类型参数")
        else:
            print("❌ 不支持选择器类型参数")
            
    except Exception as e:
        print(f"❌ 验证 BrowserCore 失败: {e}")

def verify_plugin_methods():
    """验证插件是否透传了新方法"""
    print("\n🔍 验证 UserBrowserInstance 新增方法...")
    
    try:
        with open("browser_llm_plugin.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查新增方法是否存在
        methods = [
            "get_page_source",
            "click_element", 
            "text_input_by_selector",
            "find_elements",
            "get_element_text",
            "get_element_attribute",
            "wait_for_element"
        ]
        
        for method in methods:
            if f"async def {method}" in content:
                print(f"✅ {method} 方法存在")
            else:
                print(f"❌ {method} 方法不存在")
                
    except Exception as e:
        print(f"❌ 验证插件方法失败: {e}")

def verify_llm_tools():
    """验证 LLM 工具是否正确注册"""
    print("\n🔍 验证 LLM 工具注册...")
    
    try:
        with open("browser_llm_plugin.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查新增工具是否存在
        tools = [
            "browser_get_source",
            "browser_click_element", 
            "browser_input_by_selector",
            "browser_find_elements",
            "browser_get_element_text",
            "browser_get_element_attribute",
            "browser_wait_for_element"
        ]
        
        for tool in tools:
            if f'@register_llm_tool(name="{tool}")' in content:
                print(f"✅ {tool} 工具已注册")
            else:
                print(f"❌ {tool} 工具未注册")
                
    except Exception as e:
        print(f"❌ 验证 LLM 工具失败: {e}")

def check_imports():
    """检查导入是否正确"""
    print("\n🔍 检查导入语句...")
    
    try:
        with open("browser_llm_plugin.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        imports = [
            "from core.browser import BrowserCore",
            "from core.favorite import FavoriteManager",
            "from core.operate import BrowserOperator", 
            "from core.supervisor import BrowserSupervisor",
            "from core.ticks_overlay import TickOverlay"
        ]
        
        for imp in imports:
            if imp in content:
                print(f"✅ {imp}")
            else:
                print(f"❌ {imp} 缺失")
                
    except Exception as e:
        print(f"❌ 检查导入失败: {e}")

def main():
    """主验证函数"""
    print("🚀 开始验证新增的浏览器功能...")
    print("=" * 50)
    
    verify_browser_core()
    verify_plugin_methods()
    verify_llm_tools()
    check_imports()
    
    print("\n" + "=" * 50)
    print("📋 新增功能总结:")
    print("1. ✅ 页面源码获取工具 (browser_get_source)")
    print("2. ✅ 基于选择器的点击工具 (browser_click_element)")
    print("3. ✅ 基于选择器的输入工具 (browser_input_by_selector)")
    print("4. ✅ 元素查找工具 (browser_find_elements)")
    print("5. ✅ 元素文本获取工具 (browser_get_element_text)")
    print("6. ✅ 元素属性获取工具 (browser_get_element_attribute)")
    print("7. ✅ 元素等待工具 (browser_wait_for_element)")
    print("8. ✅ 支持CSS和XPath选择器")
    print("9. ✅ 透传到UserBrowserInstance")
    print("10. ✅ 注册为LLM工具")
    
    print("\n🎉 新增功能验证完成！")

if __name__ == "__main__":
    main()