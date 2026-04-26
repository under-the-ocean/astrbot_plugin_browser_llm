# 快速使用示例

## 🎯 基础操作示例

### 1. 打开百度并搜索
```python
browser_open(url="https://www.baidu.com")
browser_input(text="人工智能")
browser_screenshot()
```

### 2. 使用选择器操作
```python
# 通过CSS选择器点击搜索按钮
browser_click_element(selector="#su", selector_type="css")

# 通过XPath选择器点击登录链接
browser_click_element(selector='//a[contains(text(), "登录")]', selector_type="xpath")
```

### 3. 获取页面信息
```python
# 获取页面源码
browser_get_source(save_to_file=True)

# 查找所有图片
browser_find_elements(selector="img", selector_type="css", attribute="src")

# 获取页面标题
title = browser_get_element_text(selector="title", selector_type="css")
```

## 📊 实际应用场景

### 场景1: 自动化登录
```python
# 步骤1: 打开登录页面
browser_open(url="https://github.com/login")

# 步骤2: 输入用户名
browser_input_by_selector(selector="#login_field", text="your_username", selector_type="css")

# 步骤3: 输入密码
browser_input_by_selector(selector="#password", text="your_password", selector_type="css")

# 步骤4: 点击登录按钮
browser_click_element(selector="input[type='submit']", selector_type="css")

# 步骤5: 等待登录完成
browser_wait_for_element(selector="nav.user-profile", timeout=10, selector_type="css")
```

### 场景2: 新闻数据采集
```python
# 步骤1: 打开新闻网站
browser_open(url="https://news.ycombinator.com")

# 步骤2: 等待页面加载
browser_wait_for_element(selector=".titleline", timeout=5, selector_type="css")

# 步骤3: 收集所有新闻标题
titles = browser_find_elements(selector=".titleline a", selector_type="css")

# 步骤4: 收集所有新闻链接
links = browser_find_elements(selector=".titleline a", selector_type="css", attribute="href")

# 步骤5: 点击第一个新闻
browser_click_element(selector=".titleline a:first-child", selector_type="css")

# 步骤6: 获取文章内容
content = browser_get_element_text(selector=".storycontent", selector_type="css")
```

### 场景3: 电商比价
```python
# 步骤1: 搜索商品
browser_open(url="https://www.amazon.com")
browser_input_by_selector(selector="#twotabsearchtextbox", text="iPhone 15", selector_type="css")
browser_click_element(selector="#nav-search-submit-button", selector_type="css")

# 步骤2: 等待搜索结果
browser_wait_for_element(selector=".s-result-item", timeout=10, selector_type="css")

# 步骤3: 获取商品信息
products = browser_find_elements(selector=".s-result-item", selector_type="css")

# 步骤4: 获取价格信息
for i, product in enumerate(products[:5]):
    price = browser_get_element_attribute(selector=f".s-result-item:nth-child({i+1}) .a-price-whole", attribute_name="textContent", selector_type="css")
    title = browser_get_element_text(selector=f".s-result-item:nth-child({i+1)} .s-title-instructions-style", selector_type="css")
    print(f"商品: {title[:50]}...")
    print(f"价格: {price}")
```

## 🎨 选择器语法速查

### CSS 选择器
| 选择器 | 示例 | 说明 |
|--------|------|------|
| ID | `#header` | ID为header的元素 |
| 类名 | `.container` | 类名为container的元素 |
| 标签 | `div` | 所有div元素 |
| 属性 | `[type="text"]` | type属性为text的元素 |
| 后代 | `div p` | div内的所有p元素 |
| 子元素 | `div > p` | div的直接子元素p |
| 伪类 | `:first-child` | 第一个子元素 |

### XPath 选择器
| 选择器 | 示例 | 说明 |
|--------|------|------|
| 绝对路径 | `/html/body/div` | 从根开始的路径 |
| 相对路径 | `//div` | 所有div元素 |
| 属性匹配 | `//*[@id='header']` | ID为header的元素 |
| 文本包含 | `//*[contains(text(), '登录')]` | 包含"登录"文本的元素 |
| 属性组合 | `//input[@type='text' and @name='search']` | 同时满足两个属性的元素 |

## ⚡ 最佳实践

### 1. 选择器优先级
```python
# 优先使用ID选择器（最快）
browser_click_element(selector="#submit-btn", selector_type="css")

# 其次是类名选择器
browser_click_element(selector=".btn-primary", selector_type="css")

# 最后是标签选择器（最慢）
browser_click_element(selector="button", selector_type="css")
```

### 2. 等待策略
```python
# 等待元素出现后再操作
browser_wait_for_element(selector=".loading-spinner", timeout=5, selector_type="css")

# 等待元素消失
browser_wait_for_element(selector=".loading-spinner", timeout=10, selector_type="css")
```

### 3. 错误处理
```python
# 使用try-catch处理可能的错误
try:
    browser_click_element(selector="#submit-btn", selector_type="css")
except Exception as e:
    print(f"点击失败: {e}")
    # 可以尝试备用选择器
    browser_click_element(selector="button[type='submit']", selector_type="css")
```

## 🔍 调试技巧

### 1. 查找元素信息
```python
# 查找所有按钮
buttons = browser_find_elements(selector="button", selector_type="css")
for i, button in enumerate(buttons):
    print(f"按钮 {i+1}: {button}")
```

### 2. 验证选择器
```python
# 检查元素是否存在
text = browser_get_element_text(selector="#non-existent-element", selector_type="css")
if text:
    print("元素存在")
else:
    print("元素不存在")
```

### 3. 获取页面源码调试
```python
# 获取页面源码用于调试
source = browser_get_source(save_to_file=True)
# 可以在源码中查找选择器是否正确
```

---

**提示**: 这些工具支持组合使用，可以根据实际需求灵活组合各种操作来实现复杂的自动化任务。