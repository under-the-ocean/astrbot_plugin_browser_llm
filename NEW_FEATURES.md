# 新增浏览器功能说明

## 🌟 概述

为 AstrBot LLM 浏览器插件新增了两个重要功能：
1. **页面源码获取工具** - 获取当前页面的 HTML 源代码
2. **基于选择器的操作工具** - 支持通过 CSS 和 XPath 选择器精确操作页面元素

## 📋 新增工具列表

### 1. 页面源码获取工具

#### `browser_get_source`
- **功能**: 获取当前页面的 HTML 源代码
- **参数**:
  - `save_to_file` (boolean): 是否保存到文件，默认 `false`
- **使用示例**:
  ```python
  # 获取页面源码（截取前5000字符）
  browser_get_source()
  
  # 获取完整页面源码并保存到文件
  browser_get_source(save_to_file=True)
  ```

### 2. 基于选择器的操作工具

#### `browser_click_element`
- **功能**: 通过选择器点击元素
- **参数**:
  - `selector` (string): 选择器表达式
  - `selector_type` (string): 选择器类型，"css" 或 "xpath"，默认 "css"
- **使用示例**:
  ```python
  # 通过CSS选择器点击
  browser_click_element(selector="#submit-btn", selector_type="css")
  
  # 通过XPath选择器点击
  browser_click_element(selector='//button[contains(text(), "登录")]', selector_type="xpath")
  ```

#### `browser_input_by_selector`
- **功能**: 通过选择器在输入框中输入文本
- **参数**:
  - `selector` (string): 选择器表达式
  - `text` (string): 要输入的文本
  - `selector_type` (string): 选择器类型，"css" 或 "xpath"，默认 "css"
- **使用示例**:
  ```python
  # 通过CSS选择器输入
  browser_input_by_selector(selector="#search-input", text="Python教程", selector_type="css")
  
  # 通过XPath选择器输入
  browser_input_by_selector(selector='//input[@type="text"]', text="人工智能", selector_type="xpath")
  ```

#### `browser_find_elements`
- **功能**: 查找页面元素并返回其信息
- **参数**:
  - `selector` (string): 选择器表达式
  - `selector_type` (string): 选择器类型，"css" 或 "xpath"，默认 "css"
  - `attribute` (string): 可选，指定要获取的属性名
- **使用示例**:
  ```python
  # 查找所有链接
  browser_find_elements(selector="a", selector_type="css", attribute="href")
  
  # 查找所有图片
  browser_find_elements(selector="img", selector_type="css", attribute="src")
  
  # 查找所有按钮
  browser_find_elements(selector="button", selector_type="css")
  ```

#### `browser_get_element_text`
- **功能**: 获取元素的文本内容
- **参数**:
  - `selector` (string): 选择器表达式
  - `selector_type` (string): 选择器类型，"css" 或 "xpath"，默认 "css"
- **使用示例**:
  ```python
  # 获取标题文本
  browser_get_element_text(selector="h1", selector_type="css")
  
  # 获取特定按钮文本
  browser_get_element_text(selector='//button[@id="submit"]', selector_type="xpath")
  ```

#### `browser_get_element_attribute`
- **功能**: 获取元素的指定属性值
- **参数**:
  - `selector` (string): 选择器表达式
  - `attribute_name` (string): 属性名
  - `selector_type` (string): 选择器类型，"css" 或 "xpath"，默认 "css"
- **使用示例**:
  ```python
  # 获取链接地址
  browser_get_element_attribute(selector="a", attribute_name="href", selector_type="css")
  
  # 获取图片地址
  browser_get_element_attribute(selector="img", attribute_name="src", selector_type="css")
  
  # 获取元素ID
  browser_get_element_attribute(selector="div", attribute_name="id", selector_type="css")
  ```

#### `browser_wait_for_element`
- **功能**: 等待元素出现
- **参数**:
  - `selector` (string): 选择器表达式
  - `timeout` (number): 超时时间（秒），默认30秒
  - `selector_type` (string): 选择器类型，"css" 或 "xpath"，默认 "css"
- **使用示例**:
  ```python
  # 等待登录按钮出现
  browser_wait_for_element(selector="#login-btn", timeout=10, selector_type="css")
  
  # 等待加载完成
  browser_wait_for_element(selector='//div[@class="loading"]', timeout=30, selector_type="xpath")
  ```

## 🎯 使用场景

### 1. 自动化登录
```python
# 打开登录页面
browser_open(url="https://example.com/login")

# 输入用户名
browser_input_by_selector(selector="#username", text="your_username")

# 输入密码
browser_input_by_selector(selector="#password", text="your_password")

# 点击登录按钮
browser_click_element(selector="#login-btn")

# 等待页面加载
browser_wait_for_element(selector=".dashboard", timeout=15)
```

### 2. 数据采集
```python
# 打开目标页面
browser_open(url="https://news.example.com")

# 查找所有新闻标题
titles = browser_find_elements(selector="h2.news-title", selector_type="css")

# 获取所有新闻链接
links = browser_find_elements(selector="a.news-link", selector_type="css", attribute="href")

# 获取第一篇新闻的详细内容
browser_click_element(selector="a.news-link:first-child")
text = browser_get_element_text(selector=".article-content")
```

### 3. 网站测试
```python
# 打开测试页面
browser_open(url="https://test.example.com")

# 等待关键元素出现
browser_wait_for_element(selector="#main-content", timeout=5)

# 验证页面元素
title = browser_get_element_text(selector="h1")
if "Welcome" not in title:
    print("页面标题不符合预期")

# 测试表单提交
browser_input_by_selector(selector="#test-input", text="test_value")
browser_click_element(selector="#submit-btn")
```

## 📝 选择器语法参考

### CSS 选择器示例
- `#id` - 通过ID选择
- `.class` - 通过类名选择
- `element` - 通过标签名选择
- `[attribute=value]` - 通过属性选择
- `:first-child` - 第一个子元素
- `:visible` - 可见元素
- `input[type="text"]` - 特定类型的输入框

### XPath 选择器示例
- `//div` - 所有div元素
- `//*[@id='example']` - ID为example的元素
- `//button[contains(text(), '登录')]` - 包含"登录"文本的按钮
- `//div[@class='container']//h1` - 容器内的所有h1
- `//input[@type='text' and @name='search']` - 特定属性组合的输入框

## 🔧 技术特性

1. **双选择器支持**: 同时支持 CSS 和 XPath 选择器
2. **智能元素解析**: 自动处理元素可见性、状态等
3. **错误处理**: 完善的异常处理和错误提示
4. **截图集成**: 操作后自动更新截图
5. **超时控制**: 支持自定义超时时间
6. **属性提取**: 可获取任意元素属性

## 🚀 集成方式

这些工具已经完全集成到现有的 AstrBot LLM 浏览器插件中，无需额外配置。AI 可以直接调用这些工具来执行复杂的浏览器操作任务。

## 📞 支持

如果在使用过程中遇到问题，请检查：
1. 选择器语法是否正确
2. 页面是否完全加载
3. 元素是否可见且可交互
4. 网络连接是否稳定

---

**版本**: v2.0.0  
**更新日期**: 2026-04-26  
**作者**: AstrBot Team