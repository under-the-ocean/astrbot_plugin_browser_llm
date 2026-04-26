#!/usr/bin/env python3
"""
快速检查Chromium浏览器
"""

import subprocess
import sys

def check_chromium():
    """快速检查Chromium是否可用"""
    print("=== 快速检查Chromium浏览器 ===")
    
    # 检查playwright是否已安装
    try:
        result = subprocess.run([sys.executable, "-m", "playwright", "list"], 
                              capture_output=True, text=True, timeout=10)
        print("✓ Playwright已安装")
        print("已安装的浏览器:")
        print(result.stdout)
    except subprocess.TimeoutExpired:
        print("✗ Playwright命令超时")
        return False
    except subprocess.CalledProcessError as e:
        print(f"✗ Playwright检查失败: {e}")
        return False
    
    # 检查chromium是否已下载
    try:
        result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                              capture_output=True, text=True, timeout=30)
        if "already installed" in result.stdout.lower():
            print("✓ Chromium浏览器已安装")
            return True
        else:
            print("正在安装Chromium浏览器...")
            print("安装完成")
            return True
    except subprocess.TimeoutExpired:
        print("✗ Chromium安装超时")
        return False
    except subprocess.CalledProcessError as e:
        print(f"✗ Chromium安装失败: {e}")
        return False

if __name__ == "__main__":
    if check_chromium():
        print("\n🎉 Chromium浏览器检查通过！")
        print("现在可以运行完整的插件测试了。")
    else:
        print("\n❌ Chromium浏览器检查失败，请先安装Chromium浏览器。")