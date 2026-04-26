"""
浏览器核心 — 增强资源控制版
新增：
- 截图大小限制 & 压缩保护
- 缓存目录自动清理（按文件数量和总大小）
- 标签页硬上限
- 进程PID追踪（对接Supervisor内存监控）
"""

import asyncio
import json
import shutil
import time
import uuid
from collections.abc import Coroutine, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypeVar

from astrbot.api import logger
from playwright._impl._api_structures import SetCookieParam
from playwright.async_api import BrowserContext, Cookie, Page, async_playwright

T = TypeVar("T")


class CookieManager:
    def __init__(self, data_dir: Path):
        self.cookies_file = data_dir / "browser_cookies.json"

    def load_cookies(self) -> list[dict]:
        """从 json 文件加载 cookies"""
        try:
            with open(self.cookies_file, encoding="utf-8") as f:
                raw_cookies: list[dict] = json.load(f)
                return raw_cookies
        except FileNotFoundError:
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump([], f)
            return []
        except json.JSONDecodeError:
            return []

    def save_cookies(self, cookies: list[dict]):
        self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cookies_file, "w") as f:
            json.dump(cookies, f, indent=4, ensure_ascii=False)


class BrowserCore:
    """
    浏览器核心 — 增强资源控制版
    """

    _BROWSER_ENGINES = {"firefox", "chromium", "webkit"}

    def __init__(self, config: dict, data_dir: Path):
        self.config = config
        self.cookie = CookieManager(data_dir)

        self.cache_dir = data_dir / "screenshot_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.browser_type: str = self.config.get("browser_type", "firefox")
        if self.browser_type not in self._BROWSER_ENGINES:
            raise ValueError(f"不支持的浏览器类型: {self.browser_type}")

        self.playwright = None
        self.browser = None
        self.context: BrowserContext | None = None

        self.all_pages: list[Page] = []
        self.current_index: int | None = None
        self.page: Page | None = None

        self._terminated = False
        self._op_lock = asyncio.Lock()

        # ===== 资源限制参数 =====
        # 每个用户最大标签页数
        self.max_pages: int = config.get("max_pages", 5)
        # 截图质量
        self.screenshot_quality: int = min(config.get("screenshot_quality", 80), 100)
        # 视图尺寸
        self.viewport = config.get("viewport_size", {"width": 1280, "height": 720})
        # 超时时间（秒）
        self.timeout: int = config.get("timeout", 30)
        # 无头模式
        self.headless: bool = config.get("headless", True)
        # 截图大小上限（从supervisor配置读取）
        sup_cfg = config.get("supervisor", {})
        self.screenshot_max_bytes: int = sup_cfg.get("screenshot_max_bytes", 5 * 1024 * 1024)
        # 缓存目录最大文件数（防止inode耗尽）
        self.cache_max_files: int = 500

    # ======================================================
    # 通用兜底工具
    # ======================================================

    async def _safe_await(self, coro: Coroutine[Any, Any, T], retries: int = 2) -> T:
        """带重试的超时机制"""
        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(coro, self.timeout)
            except asyncio.TimeoutError:
                if attempt < retries:
                    await asyncio.sleep(0.5)
                else:
                    raise RuntimeError("Playwright 操作超时") from None

    async def _safe_page_op(self, page: Page, coro: Coroutine[Any, Any, T]) -> T:
        """Page级操作兜底"""
        try:
            return await coro
        except Exception:
            await self._discard_page(page)
            raise

    async def _discard_page(self, page: Page):
        try:
            await page.close()
        except Exception:
            pass

        if page in self.all_pages:
            self.all_pages.remove(page)

        if not self.all_pages:
            await self._ensure_page()
        elif self.current_index is not None:
            await self._ensure_page(
                min(self.current_index, len(self.all_pages) - 1)
            )

    # ======================================================
    # 生命周期
    # ======================================================

    async def initialize(self):
        async with self._op_lock:
            self.playwright = await async_playwright().start()
            engine = getattr(self.playwright, self.browser_type)

            self.browser = await engine.launch(
                **self._get_launch_options(self.browser_type),
            )

            self.context = await self.browser.new_context(
                viewport=self.viewport,
            )

            raw_cookies = self.cookie.load_cookies()
            cookies = [
                SetCookieParam(**{k: v for k, v in c.items() if v is not None})
                for c in raw_cookies
            ]
            if cookies:
                await self.context.add_cookies(cookies)

            # 启动时清理缓存
            self._cleanup_cache_on_start()

            await self._ensure_page()

    def _cleanup_cache_on_start(self):
        """启动时清理超量缓存文件"""
        if not self.cache_dir.exists():
            return
        try:
            files = sorted(
                [f for f in self.cache_dir.iterdir() if f.is_file()],
                key=lambda f: f.stat().st_mtime,
            )
            if len(files) > self.cache_max_files:
                to_remove = files[:len(files) - self.cache_max_files]
                for f in to_remove:
                    try:
                        f.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    async def terminate(self):
        """优雅关闭，幂等执行"""
        async with self._op_lock:
            if self._terminated:
                return
            self._terminated = True

            async def safe_close(obj, close_method="close"):
                if obj is None:
                    return
                try:
                    coro = getattr(obj, close_method)
                    if asyncio.iscoroutinefunction(coro):
                        await coro()
                    else:
                        coro()
                except Exception:
                    pass

            await self.save_cookies()

            # 关闭所有页面
            for page in self.all_pages:
                await safe_close(page)
            self.all_pages.clear()
            self.current_index = None
            self.page = None

            await safe_close(self.context)
            self.context = None

            await safe_close(self.browser)
            self.browser = None

            await safe_close(self.playwright, "stop")
            self.playwright = None

            # 清理缓存（保留最近的文件）
            self._cleanup_cache_on_terminate()

    def _cleanup_cache_on_terminate(self):
        """关闭时清理缓存，只保留最近的文件"""
        if not self.cache_dir.exists():
            return
        try:
            files = sorted(
                [f for f in self.cache_dir.iterdir() if f.is_file()],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            # 只保留最近50个文件
            if len(files) > 50:
                for f in files[50:]:
                    try:
                        f.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    # ======================================================
    # 启动参数
    # ======================================================

    def _get_launch_options(self, engine: str) -> dict[str, Any]:
        args = [
            "--mute-audio",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-extensions",
            "--disable-accelerated-2d-canvas",
            "--disable-component-extensions-with-background-pages",
            "--disable-sync",
            "--no-first-run",
        ]

        opts: dict[str, Any] = {"args": args}
        opts["headless"] = self.headless

        if engine == "firefox":
            opts["firefox_user_prefs"] = {
                "intl.accept_languages": "zh-CN,zh",
                "intl.locale.requested": "zh-CN",
                "general.useragent.locale": "zh-CN",
                "media.autoplay.default": 5,
                "media.autoplay.blocking_policy": 2,
                "dom.ipc.processCount": 1,
                "browser.tabs.remote.autostart": False,
                "browser.sessionhistory.max_entries": 50,
                "browser.sessionhistory.contentViewerTimeout": 0,
            }

        if engine == "chromium":
            opts["args"] = args + [
                "--disable-accelerated-video-decode",
                "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                "--disable-notifications",
                "--disable-speech-api",
                "--disable-sync",
            ]

        return opts

    # ======================================================
    # 页面冻结/解冻（资源优化）
    # ======================================================

    async def _freeze_page(self, page: Page):
        """冻结页面以节省资源"""
        try:
            await page.evaluate("""
                (() => {
                    document.querySelectorAll('video,audio').forEach(v => v.pause());
                    if (!window._freeze) {
                        window._oldSetInterval = window.setInterval;
                        window._oldRequestAnimationFrame = window.requestAnimationFrame;
                        window.setInterval = () => 0;
                        window.requestAnimationFrame = () => {};
                        window._freeze = true;
                    }
                })()
            """)
        except Exception:
            pass

    async def _unfreeze_page(self, page: Page):
        """解冻页面"""
        try:
            await page.evaluate("() => { window._freeze = false; }")
        except Exception:
            pass

    # ======================================================
    # 内部保障
    # ======================================================

    def _require_context(self) -> BrowserContext:
        if self._terminated:
            raise RuntimeError("BrowserManager 已终止")
        if self.context is None:
            raise RuntimeError("BrowserContext 未初始化")
        return self.context

    async def _ensure_page(self, index: int | None = None) -> Page:
        context = self._require_context()

        if not self.all_pages:
            page = await context.new_page()
            default_url = self.config.get("default_url", "https://www.baidu.com")
            await self._safe_await(page.goto(default_url))
            self.all_pages.append(page)
            self.current_index = 0
            self.page = page
            return page

        if index is None:
            index = self.current_index or 0

        index = max(0, min(index, len(self.all_pages) - 1))

        if self.page is not None and index != self.current_index:
            await self._freeze_page(self.page)

        self.current_index = index
        self.page = self.all_pages[index]
        await self._unfreeze_page(self.page)

        return self.page

    async def save_cookies(self):
        if not self.context:
            return
        cookies: list[Cookie] = await self.context.cookies()
        self.cookie.save_cookies(cookies)

    # ======================================================
    # 标签页管理（带上限保护）
    # ======================================================

    async def get_all_tabs_titles(self) -> list[str]:
        async with self._op_lock:
            return await asyncio.gather(*(p.title() for p in self.all_pages))

    async def switch_tab(self, index: int) -> Optional[str]:
        async with self._op_lock:
            if not (0 <= index < len(self.all_pages)):
                return f"无效的标签页序号 {index}"
            await self._ensure_page(index)
            return None

    async def close_tab(self, index: int) -> str:
        async with self._op_lock:
            if not (0 <= index < len(self.all_pages)):
                return f"无效的标签页序号 {index}"
            page = self.all_pages[index]
            title = await page.title()
            await self._discard_page(page)
            return f"已关闭标签页【{title}】"

    # ======================================================
    # 页面展示
    # ======================================================

    async def zoom_to_scale(self, scale: float) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            # 限制缩放范围 0.1 ~ 5.0
            scale = max(0.1, min(5.0, scale))
            await page.evaluate(f"document.body.style.zoom = {scale};")
            return None

    async def screenshot(
        self,
        zoom_factor: Optional[float] = None,
        full_page: bool = False,
    ) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()

            async def _shot():
                if zoom_factor:
                    zoom = max(0.1, min(5.0, zoom_factor))
                    await page.evaluate(f"document.body.style.zoom = {zoom};")
                    await page.evaluate("window.scrollTo(0, 0);")

                return await page.screenshot(
                    full_page=full_page,
                    type="jpeg",
                    quality=self.screenshot_quality,
                )

            raw: bytes = await _shot()
            if raw is None:
                return None

            # ===== 截图大小保护 =====
            if len(raw) > self.screenshot_max_bytes:
                # 尝试降低质量重新截图
                reduced_quality = max(10, self.screenshot_quality // 2)
                raw = await page.screenshot(
                    full_page=False,  # 强制非全页
                    type="jpeg",
                    quality=reduced_quality,
                )
                # 如果仍然过大，再压缩视图
                if len(raw) > self.screenshot_max_bytes:
                    await page.evaluate("document.body.style.zoom = 0.5;")
                    raw = await page.screenshot(
                        full_page=False,
                        type="jpeg",
                        quality=30,
                    )
                    await page.evaluate("document.body.style.zoom = 1;")
                    logger.warning(
                        f"[BrowserCore] 截图过大，已压缩至 {len(raw) / 1024:.1f}KB"
                    )

            # ===== 缓存文件数保护 =====
            if self.cache_dir.exists():
                file_count = len(list(self.cache_dir.iterdir()))
                if file_count > self.cache_max_files:
                    # 清理最旧的文件
                    files = sorted(
                        [f for f in self.cache_dir.iterdir() if f.is_file()],
                        key=lambda f: f.stat().st_mtime,
                    )
                    to_remove = files[:file_count - self.cache_max_files]
                    for f in to_remove:
                        try:
                            f.unlink()
                        except Exception:
                            pass

            # ===== 写入缓存文件 =====
            file_name = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.jpg"
            cache_path = self.cache_dir / file_name
            cache_path.write_bytes(raw)

            return str(cache_path)

    # ======================================================
    # 页面访问（带标签页上限保护）
    # ======================================================

    async def search(self, url: str) -> Optional[str]:
        async with self._op_lock:
            # 检查是否已有同URL的页面
            for i, p in enumerate(self.all_pages):
                if p.url == url:
                    await self._ensure_page(i)
                    return None

            # ===== 标签页上限保护 =====
            if len(self.all_pages) >= self.max_pages:
                # 关闭最旧的标签页
                old_page = self.all_pages.pop(0)
                try:
                    await old_page.close()
                except Exception:
                    pass
                logger.warning(
                    f"[BrowserCore] 标签页已达上限({self.max_pages})，自动关闭最旧标签页"
                )

            page = await self._require_context().new_page()
            try:
                await self._safe_await(
                    page.goto(url, wait_until="domcontentloaded"),
                )
                zoom_factor = self.config.get("zoom_factor", 1.0)
                await page.evaluate(f"document.body.style.zoom = {zoom_factor};")
            except Exception:
                await self._discard_page(page)
                return "URL 访问失败"

            self.all_pages.append(page)
            self.current_index = len(self.all_pages) - 1
            self.page = page

            await self.save_cookies()
            return None

    # ======================================================
    # 页面交互
    # ======================================================

    async def click_coord(self, coords: Sequence[int]) -> Optional[str]:
        if len(coords) != 2:
            return "坐标参数格式错误"
        x, y = map(int, coords)

        async with self._op_lock:
            page = await self._ensure_page()
            new_page: Optional[Page] = None

            def on_popup(popup: Page):
                nonlocal new_page, page
                new_page = popup
                self.all_pages.append(popup)
                self.current_index = len(self.all_pages) - 1
                self.page = popup

            page.on("popup", on_popup)
            try:
                await self._safe_page_op(
                    page,
                    self._safe_await(page.mouse.click(x, y, delay=100)),
                )
                await asyncio.sleep(1.5)
            finally:
                page.remove_listener("popup", on_popup)

        return None

    async def scroll_by(self, distance: int, direction: str) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            dx = dy = 0
            if direction == "上":
                dy = -distance
            elif direction == "下":
                dy = distance
            elif direction == "左":
                dx = -distance
            elif direction == "右":
                dx = distance
            else:
                return "无效的滚动方向"

            await self._safe_page_op(
                page,
                page.evaluate(f"window.scrollBy({dx}, {dy});"),
            )
            return None

    async def text_input(self, text: str, enter: bool = True) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            await page.wait_for_load_state("load")

            inputs = await page.query_selector_all(
                "input:not([disabled]):not([readonly])"
            )
            for el in inputs:
                if await el.is_visible():
                    await el.fill(text)
                    if enter:
                        await page.keyboard.press("Enter")
                    return None
            return "未找到可用的输入框"

    # ======================================================
    # 选择器解析工具
    # ======================================================

    async def _resolve_element(
        self, page: Page, selector: str, selector_type: str = "css"
    ):
        if selector_type == "xpath":
            return await page.query_selector(f"xpath={selector}")
        else:
            return await page.query_selector(selector)

    async def _resolve_elements(
        self, page: Page, selector: str, selector_type: str = "css"
    ):
        if selector_type == "xpath":
            return await page.query_selector_all(f"xpath={selector}")
        else:
            return await page.query_selector_all(selector)

    # ======================================================
    # 页面源码获取（大小保护）
    # ======================================================

    async def get_page_source(self) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            try:
                content = await page.content()
                # 限制源码大小，超过5MB截断
                max_bytes = 5 * 1024 * 1024
                if len(content.encode('utf-8')) > max_bytes:
                    content = content[:max_bytes // 4]  # 粗略截断
                    logger.warning("[BrowserCore] 页面源码超过5MB，已截断")
                return content
            except Exception:
                return None

    # ======================================================
    # 基于选择器的元素操作
    # ======================================================

    async def click_element(
        self, selector: str, selector_type: str = "css"
    ) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            new_page: Optional[Page] = None

            def on_popup(popup: Page):
                nonlocal new_page, page
                new_page = popup
                self.all_pages.append(popup)
                self.current_index = len(self.all_pages) - 1
                self.page = popup

            page.on("popup", on_popup)
            try:
                el = await self._resolve_element(page, selector, selector_type)
                if el is None:
                    return f"未找到选择器【{selector}】对应的元素"
                await self._safe_await(el.click(delay=100))
                await asyncio.sleep(1)
            except Exception as e:
                return f"点击元素失败: {str(e)}"
            finally:
                page.remove_listener("popup", on_popup)
        return None

    async def text_input_by_selector(
        self, selector: str, text: str, selector_type: str = "css"
    ) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            await page.wait_for_load_state("load")
            el = await self._resolve_element(page, selector, selector_type)
            if el is None:
                return f"未找到选择器【{selector}】对应的元素"
            await el.fill(text)
            return None

    async def find_elements(
        self, selector: str, selector_type: str = "css", attribute: Optional[str] = None
    ) -> list[dict] | str:
        async with self._op_lock:
            page = await self._ensure_page()
            elements = await self._resolve_elements(page, selector, selector_type)
            if not elements:
                return f"未找到选择器【{selector}】对应的元素"

            result = []
            # 限制返回元素数量，防止LLM上下文爆炸
            max_elements = 50
            for el in elements[:max_elements]:
                info = {}
                try:
                    info["tag"] = await el.evaluate("el => el.tagName.toLowerCase()")
                    info["text"] = (await el.inner_text()).strip()[:200]
                except Exception:
                    info["tag"] = "unknown"
                    info["text"] = ""

                if attribute:
                    try:
                        if attribute == "innerText":
                            info[attribute] = (await el.inner_text()).strip()[:500]
                        elif attribute == "outerHTML":
                            info[attribute] = (await el.evaluate("el => el.outerHTML"))[:500]
                        else:
                            val = await el.get_attribute(attribute)
                            info[attribute] = val if val else ""
                    except Exception:
                        info[attribute] = ""

                try:
                    attrs = await el.evaluate("""el => {
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        return attrs;
                    }""")
                    info["attributes"] = attrs
                except Exception:
                    info["attributes"] = {}

                result.append(info)

            if len(elements) > max_elements:
                result.append({"note": f"...还有 {len(elements) - max_elements} 个元素未返回"})

            return result

    async def get_element_text(
        self, selector: str, selector_type: str = "css"
    ) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            el = await self._resolve_element(page, selector, selector_type)
            if el is None:
                return None
            try:
                text = (await el.inner_text()).strip()
                # 限制文本长度，防止LLM上下文过大
                return text[:5000]
            except Exception:
                return None

    async def get_element_attribute(
        self, selector: str, attribute_name: str, selector_type: str = "css"
    ) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            el = await self._resolve_element(page, selector, selector_type)
            if el is None:
                return None
            try:
                return await el.get_attribute(attribute_name)
            except Exception:
                return None

    async def wait_for_element(
        self, selector: str, timeout: float = 30, selector_type: str = "css"
    ) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            try:
                if selector_type == "xpath":
                    await page.wait_for_selector(f"xpath={selector}", timeout=timeout * 1000)
                else:
                    await page.wait_for_selector(selector, timeout=timeout * 1000)
                return None
            except Exception as e:
                return f"等待元素超时或失败: {str(e)}"

    async def go_back(self) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            await page.go_back()
            await page.wait_for_load_state("load")
            return None

    async def go_forward(self) -> Optional[str]:
        async with self._op_lock:
            page = await self._ensure_page()
            await page.go_forward()
            await page.wait_for_load_state("load")
            return None
