"""
浏览器资源监控器 — 增强版
支持：
- 进程级内存监控（单个浏览器进程）
- 整体服务器内存监控
- 闲置自动关闭
- 截图缓存目录大小监控与自动清理
- 操作频率限制（熔断）
- 硬超时熔断
"""

import asyncio
import os
import shutil
import time
import traceback
from pathlib import Path
from typing import Any, Optional

import psutil

from astrbot.api import logger


class BrowserSupervisor:
    """
    增强版浏览器资源监控器
    每个用户浏览器实例对应一个监控器
    """

    def __init__(self, config: dict, data_dir: str):
        self.config = config
        sup_cfg: dict[str, Any] = config.get("supervisor", {})

        # ===== 内存限制 =====
        # 服务器整体内存阈值（百分比）
        self.max_memory_percent: int = sup_cfg.get("max_memory_percent", 80)
        # 单个浏览器进程最大内存（MB）
        self.max_process_memory_mb: int = sup_cfg.get("max_process_memory_mb", 512)

        # ===== 闲置超时 =====
        self.idle_timeout: int = sup_cfg.get("idle_timeout", 600)  # 默认10分钟

        # ===== 监控间隔 =====
        self.monitor_interval: float = sup_cfg.get("monitor_interval", 10.0)

        # ===== 缓存清理 =====
        self.cache_max_size_mb: int = sup_cfg.get("cache_max_size_mb", 200)
        self.cache_max_age_hours: int = sup_cfg.get("cache_max_age_hours", 2)

        # ===== 操作频率限制 =====
        self.max_operations_per_minute: int = sup_cfg.get("max_operations_per_minute", 20)

        # ===== 截图大小限制 =====
        self.screenshot_max_bytes: int = sup_cfg.get("screenshot_max_bytes", 5 * 1024 * 1024)  # 5MB

        # ===== 硬超时 =====
        self.hard_operation_timeout: int = sup_cfg.get("hard_operation_timeout", 60)

        self.browser_type = config.get("browser_type", "firefox")
        self.verify_browser = config.get("verify_browser", True)

        self.data_dir = data_dir
        self.cache_dir = Path(data_dir) / "screenshot_cache"

        self.browser = None  # BrowserCore 实例

        self._call_lock = asyncio.Lock()
        self._browser_lock = asyncio.Lock()

        self._last_active: float = time.time()
        self._monitor_task: Optional[asyncio.Task] = None

        # ===== 操作频率统计 =====
        self._operation_timestamps: list[float] = []
        self._rate_limit_lock = asyncio.Lock()

        # ===== 浏览器进程PID追踪 =====
        self._browser_pids: list[int] = []

    # =====================================================
    # 生命周期
    # =====================================================

    async def start(self):
        """启动监控协程"""
        async with self._call_lock:
            if self._monitor_task is None or self._monitor_task.done():
                self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """停止监控和浏览器"""
        async with self._call_lock:
            if self._monitor_task and not self._monitor_task.done():
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
                self._monitor_task = None

            if self.browser:
                try:
                    await self.browser.terminate()
                except Exception:
                    pass
                self.browser = None
            self._browser_pids.clear()

    # =====================================================
    # 操作频率限制（熔断检查）
    # =====================================================

    async def check_rate_limit(self) -> bool:
        """
        检查是否触发操作频率限制。
        返回 True = 允许操作，False = 触发熔断。
        """
        async with self._rate_limit_lock:
            now = time.time()
            # 移除60秒前的记录
            cutoff = now - 60
            self._operation_timestamps = [
                t for t in self._operation_timestamps if t > cutoff
            ]
            # 检查是否超出限制
            if len(self._operation_timestamps) >= self.max_operations_per_minute:
                logger.warning(
                    f"[Supervisor] 操作频率限制触发: "
                    f"{len(self._operation_timestamps)}次/分钟 "
                    f"(上限{self.max_operations_per_minute})"
                )
                return False
            # 记录本次操作
            self._operation_timestamps.append(now)
            return True

    async def reset_rate_limit(self):
        """重置频率限制计数器（例如关闭浏览器时）"""
        async with self._rate_limit_lock:
            self._operation_timestamps.clear()

    # =====================================================
    # 对外调用接口（带超时和频率限制）
    # =====================================================

    async def call(self, method: str, **kwargs):
        """调用浏览器方法，带超时和频率限制"""
        # 频率限制检查
        allowed = await self.check_rate_limit()
        if not allowed:
            raise RuntimeError(
                f"操作过于频繁（上限 {self.max_operations_per_minute} 次/分钟），"
                f"请稍后再试"
            )

        async with self._call_lock:
            if not self.browser:
                await self._start_browser()

            async with self._browser_lock:
                browser = self.browser
                if not browser:
                    return None
                func = getattr(browser, method, None)

            if func is None:
                raise AttributeError(f"BrowserCore 没有方法 {method}")

            self._last_active = time.time()

            # 带硬超时的调用
            try:
                return await asyncio.wait_for(
                    func(**kwargs),
                    timeout=self.hard_operation_timeout
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"[Supervisor] 操作 {method} 超时 "
                    f"(>{self.hard_operation_timeout}s)，强制终止"
                )
                # 超时后尝试重启浏览器
                asyncio.create_task(self._restart_browser())
                raise RuntimeError(
                    f"操作超时（超过 {self.hard_operation_timeout} 秒），"
                    f"浏览器已自动重启"
                )

    # =====================================================
    # 浏览器生命周期管理
    # =====================================================

    async def _start_browser(self):
        """启动浏览器并追踪其进程PID"""
        async with self._browser_lock:
            if not self.browser:
                if self.verify_browser:
                    from .downloader import BrowserDownloader
                    if not await BrowserDownloader.verify_browser(self.browser_type):
                        logger.error("浏览器未安装或不可用")
                        raise RuntimeError("浏览器未安装或不可用")

                from .browser import BrowserCore

                core = BrowserCore(self.config, Path(self.data_dir))
                try:
                    await core.initialize()
                except Exception:
                    logger.error("[Supervisor] BrowserCore.initialize 失败")
                    raise

                self.browser = core
                self._last_active = time.time()
                self._operation_timestamps.clear()

                # 异步追踪浏览器子进程PID
                asyncio.create_task(self._track_browser_pids())

    async def _track_browser_pids(self):
        """追踪浏览器引擎的子进程PID（延迟获取，等进程启动）"""
        await asyncio.sleep(3)
        if not self.browser:
            return
        try:
            pids = []
            browser_obj = self.browser.browser
            if browser_obj and browser_obj.contexts:
                for context in browser_obj.contexts:
                    for page in context.pages:
                        try:
                            pid = await page.evaluate("() => 1")  # 测试连接
                            # 通过 psutil 查找关联的浏览器进程
                            for proc in psutil.process_iter(['pid', 'name']):
                                proc_name = proc.info.get('name', '').lower() or ''
                                if any(kw in proc_name for kw in
                                       ['chromium', 'chrome', 'firefox', 'geckodriver', 'msedge']):
                                    if proc.pid not in pids:
                                        pids.append(proc.pid)
                        except Exception:
                            pass
            self._browser_pids = list(set(pids))
            if pids:
                logger.debug(f"[Supervisor] 追踪到浏览器进程PID: {pids}")
        except Exception:
            pass  # 追踪失败不影响主流程

    async def _stop_browser(self):
        """停止浏览器并清理"""
        async with self._browser_lock:
            if self.browser:
                try:
                    await self.browser.terminate()
                except Exception:
                    logger.error("[Supervisor] BrowserCore.terminate 失败")
                self.browser = None
                self._browser_pids.clear()
                await self.reset_rate_limit()
                self._last_active = time.time()

    async def _restart_browser(self):
        """重启浏览器（异步，由监控或超时触发）"""
        logger.warning("[Supervisor] 浏览器重启中...")
        await self._stop_browser()
        await asyncio.sleep(2)
        try:
            await self._start_browser()
            logger.info("[Supervisor] 浏览器重启完成")
        except Exception as e:
            logger.error(f"[Supervisor] 浏览器重启失败: {e}")

    # =====================================================
    # 缓存清理
    # =====================================================

    async def _cleanup_cache(self):
        """清理截图缓存目录：按大小和时效"""
        if not self.cache_dir.exists():
            return

        try:
            # 1. 计算总大小
            total_size = 0
            files = []
            for f in self.cache_dir.iterdir():
                if f.is_file():
                    try:
                        stat = f.stat()
                        total_size += stat.st_size
                        files.append((f, stat.st_mtime, stat.st_size))
                    except Exception:
                        continue

            max_bytes = self.cache_max_size_mb * 1024 * 1024
            now = time.time()
            max_age_seconds = self.cache_max_age_hours * 3600

            # 2. 按修改时间排序（最旧在前）
            files.sort(key=lambda x: x[1])

            removed_count = 0
            removed_size = 0

            for fpath, mtime, fsize in files:
                should_remove = False

                # 超过时效
                if now - mtime > max_age_seconds:
                    should_remove = True
                # 超过总大小限制
                elif total_size > max_bytes:
                    should_remove = True

                if should_remove:
                    try:
                        fpath.unlink()
                        removed_count += 1
                        removed_size += fsize
                        total_size -= fsize
                    except Exception:
                        continue

            if removed_count > 0:
                logger.info(
                    f"[Supervisor] 缓存清理: 删除了 {removed_count} 个文件, "
                    f"释放 {removed_size / 1024 / 1024:.1f}MB"
                )

        except Exception as e:
            logger.error(f"[Supervisor] 缓存清理异常: {e}")

    # =====================================================
    # 进程级内存检查
    # =====================================================

    async def _check_process_memory(self) -> bool:
        """
        检查浏览器子进程的内存占用。
        返回 True = 正常，False = 超出限制需要重启。
        """
        if not self._browser_pids:
            return True

        max_bytes = self.max_process_memory_mb * 1024 * 1024
        total_process_memory = 0

        for pid in list(self._browser_pids):
            try:
                proc = psutil.Process(pid)
                if not proc.is_running():
                    self._browser_pids.remove(pid)
                    continue
                mem_info = proc.memory_info()
                rss = mem_info.rss
                total_process_memory += rss

                if rss > max_bytes:
                    logger.warning(
                        f"[Supervisor] 浏览器进程 PID={pid} 内存超限: "
                        f"{rss / 1024 / 1024:.1f}MB > {self.max_process_memory_mb}MB"
                    )
                    return False

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    self._browser_pids.remove(pid)
                except ValueError:
                    pass
                continue

        # 检查总内存
        if total_process_memory > max_bytes * 2:  # 所有进程总和的宽松限制
            logger.warning(
                f"[Supervisor] 浏览器进程总内存超限: "
                f"{total_process_memory / 1024 / 1024:.1f}MB"
            )
            return False

        return True

    # =====================================================
    # 监控主循环
    # =====================================================

    async def _monitor_loop(self):
        """增强版监控循环"""
        cache_clean_interval = max(self.monitor_interval * 6, 60)  # 至少每分钟清理一次
        _cache_tick = 0

        while True:
            try:
                await asyncio.sleep(self.monitor_interval)
                _cache_tick += 1

                if not self.browser:
                    continue

                # ===== 1. 空闲检测 =====
                idle_time = time.time() - self._last_active
                if idle_time > self.idle_timeout:
                    await self._stop_browser()
                    logger.warning(
                        f"[Supervisor] 浏览器闲置超过 {self.idle_timeout}s，自动关闭"
                    )
                    continue

                # ===== 2. 服务器整体内存监控 =====
                mem = psutil.virtual_memory()
                if mem.percent > self.max_memory_percent:
                    await self._stop_browser()
                    logger.warning(
                        f"[Supervisor] 服务器内存占用过高 ({mem.percent:.1f}%)，关闭浏览器"
                    )
                    continue

                # ===== 3. 进程级内存检测 =====
                mem_ok = await self._check_process_memory()
                if not mem_ok:
                    logger.warning("[Supervisor] 浏览器进程内存超限，重启浏览器")
                    asyncio.create_task(self._restart_browser())
                    continue

                # ===== 4. 定期缓存清理 =====
                if _cache_tick * self.monitor_interval >= cache_clean_interval:
                    _cache_tick = 0
                    await self._cleanup_cache()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.error(f"[Supervisor] 监控循环异常:\n{traceback.format_exc()}")

    # =====================================================
    # 对外状态查询
    # =====================================================

    def get_status(self) -> dict:
        """获取当前监控器状态"""
        return {
            "has_browser": self.browser is not None,
            "idle_seconds": int(time.time() - self._last_active) if self.browser else -1,
            "idle_timeout": self.idle_timeout,
            "browser_pids": self._browser_pids,
            "memory_limit_mb": self.max_process_memory_mb,
            "operations_last_minute": len(
                [t for t in self._operation_timestamps if t > time.time() - 60]
            ),
            "max_operations_per_minute": self.max_operations_per_minute,
            "cache_dir": str(self.cache_dir),
            "cache_max_size_mb": self.cache_max_size_mb,
        }
