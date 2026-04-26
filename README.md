# 🌙 LLM浏览器插件 - astrbot_plugin_browser_llm

> 为 AstrBot 打造的 LLM 可调用浏览器插件，让 AI 拥有「眼睛」和「双手」。
> 
> ✨ *"月亮的赐福，为你照亮提瓦特之外的每一页。"*

---

## 🌟 简介

本插件为 [AstrBot](https://github.com/Soulter/AstrBot) 提供完整的浏览器自动化能力，支持 LLM 工具调用。每个用户拥有独立的持久化浏览器环境，突破系统 30 秒超时限制，让 AI 可以浏览网页、获取信息、与页面交互。

## ✨ 功能特性

### 🖥️ 基础浏览
- **`browser_open(url)`** — 打开指定网页
- **`browser_close()`** — 关闭浏览器
- **`browser_back()` / `browser_forward()`** — 前进 / 后退
- **`browser_screenshot()`** — 获取页面截图
- **`browser_get_source()`** — 获取页面 HTML 源码

### 🖱️ 页面交互
- **`browser_click(x, y)`** — 按坐标点击
- **`browser_input(text)`** — 在输入框中输入文本
- **`browser_scroll(direction, distance)`** — 滚动页面
- **`browser_zoom(scale)`** — 缩放页面

### 🎯 选择器操作（增强功能）
- **`browser_click_element(selector, selector_type)`** — 通过 CSS/XPath 选择器点击元素
- **`browser_input_by_selector(selector, text, selector_type)`** — 通过选择器输入文本
- **`browser_find_elements(selector, selector_type, attribute)`** — 查找页面元素
- **`browser_get_element_text(selector, selector_type)`** — 获取元素文本
- **`browser_get_element_attribute(selector, attribute_name)`** — 获取元素属性
- **`browser_wait_for_element(selector, timeout)`** — 等待元素出现

### 📑 标签页管理
- **`browser_get_tabs()`** — 获取标签页列表
- **`browser_switch_tab(index)`** — 切换标签页
- **`browser_close_tab(index)`** — 关闭标签页

## 🛠️ 安装

### 在 AstrBot 中安装

1. 将本插件目录放入 `AstrBot/data/plugins/`
2. 在 AstrBot 插件管理器中启用 `astrbot_plugin_browser_llm`
3. 发送指令 `/浏览器LLM安装` 自动安装依赖与浏览器

### 手动安装

```bash
# 安装 Playwright
pip install playwright

# 安装 Chromium 浏览器
playwright install chromium
```

## ⚙️ 配置

配置文件位于 `_conf_schema.json`，支持以下选项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `browser_type` | `chromium` | 浏览器引擎 (chromium/firefox/webkit) |
| `headless` | `true` | 是否无头模式 |
| `timeout` | `30` | 页面超时时间(秒) |
| `max_pages` | `5` | 每个用户最大标签页数 |
| `viewport_size` | `1280x720` | 视窗尺寸 |
| `screenshot_quality` | `80` | 截图质量(1-100) |

## 🔧 使用示例

```python
# 打开网页
browser_open(url="https://www.baidu.com")

# 搜索内容
browser_input(text="原神")
browser_click_element(selector="#su", selector_type="css")

# 获取页面信息
browser_get_source(save_to_file=True)
browser_screenshot()
```

## 🐛 已修复问题

- **`name 'logger' is not defined`** — `core/browser.py` 缺少 `from astrbot.api import logger` 导入
- **`cannot reuse already awaited coroutine`** — `core/browser.py` 中 `click_element` 方法协程重复 await 问题

## 📋 文件结构

```
📁 astrbot_plugin_browser_llm/
├── __init__.py              # 插件入口
├── metadata.yaml            # 插件元数据
├── main.py                  # 主逻辑
├── browser_llm_plugin.py    # LLM工具注册
├── browser_llm_plugin_simple.py  # 简化版
├── check_chromium.py        # 浏览器检查
├── quick_check.py           # 快速检查
├── verify_features.py       # 功能验证
├── _conf_schema.json        # 配置模板
├── README.md                # 本文件
├── USAGE.md                 # 使用说明
├── QUICK_EXAMPLES.md        # 快速示例
├── NEW_FEATURES.md          # 新功能说明
├── favorite.json            # 收藏夹
├── bilibili_login.py        # B站登录辅助
├── resource/                # 资源文件
│   ├── kaiti_GB2312.ttf
│   └── ticks_overlay.png
├── data/                    # 数据目录
│   ├── cmd_config.json
│   ├── plugin_data/         # 用户浏览器缓存
│   └── t2i_templates/       # 模板文件
└── core/                    # 核心模块
    ├── browser.py           # 浏览器核心
    ├── supervisor.py        # 浏览器进程管理
    ├── operate.py           # 操作接口
    ├── downloader.py        # 浏览器下载器
    ├── favorite.py          # 收藏管理
    └── ticks_overlay.py     # 水印叠加
```

## 📜 许可证

MIT License

---

<p align="center">
  🌙 <strong>under-the-ocean</strong> · 月光所至，皆为归途
</p>
# LLM Browser Plugin - Repository Info
