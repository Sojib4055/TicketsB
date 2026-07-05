from __future__ import annotations

import asyncio
import base64
import json
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import suppress
from pathlib import Path
import re
import struct
import threading
import time
from typing import Any

import yaml

from src.browser.context import ensure_browser_profile_dir
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BrowserSession:
    """
    Thin wrapper around browser automation.

    The rest of the app uses this wrapper instead of calling MCP tools directly.
    """

    _REF_PATTERN = re.compile(r"\[ref=(?P<ref>[^\]]+)\]")

    def __init__(self) -> None:
        self.connected = False
        self.current_url: str | None = None
        self._available_tools: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._owner_task: asyncio.Task[None] | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._session: Any = None
        self._snapshot_cache: dict[str, Any] = {"url": None, "text": "", "elements": [], "refs": []}
        self._selector_map = self._load_selector_map()
        ensure_browser_profile_dir()

    def connect(self) -> None:
        if self.connected:
            return

        self._ensure_loop()
        last_error: Exception | None = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                self._run_async(self._connect_async())
                self.connected = True
                logger.info("Connected to MCP browser server: %s", settings.mcp_server_url)
                return
            except Exception as exc:  # pragma: no cover - exercised in integration
                last_error = exc
                logger.warning(
                    "Failed to connect to MCP browser server on attempt %s/%s: %s",
                    attempt,
                    settings.max_retries,
                    exc,
                )
                time.sleep(1)

        raise RuntimeError(f"Unable to connect to MCP browser server at {settings.mcp_server_url}") from last_error

    def navigate(self, url: str) -> None:
        self._call_tool("browser_navigate", {"url": url})
        self.current_url = url
        self._snapshot_cache = {"url": url, "text": "", "elements": [], "refs": []}
        logger.info("Navigated to %s", url)

    def snapshot(self) -> dict[str, Any]:
        payload = self._call_tool("browser_snapshot", {})
        snapshot_text = self._extract_snapshot_text(payload)
        snapshot = {
            "url": self.current_url,
            "text": snapshot_text,
            "elements": payload.get("elements", []) if isinstance(payload, dict) else [],
            "refs": self._extract_refs(snapshot_text),
            "raw": payload,
        }
        self._snapshot_cache = snapshot
        return snapshot

    def snapshot_text(self) -> str:
        data = self.snapshot()
        return data.get("text", "")

    def click(self, semantic_target: str) -> None:
        tool_args = self._resolve_tool_args(semantic_target)
        if tool_args is not None:
            self._call_tool("browser_click", tool_args)
            self._snapshot_cache = {"url": self.current_url, "text": "", "elements": [], "refs": []}
            logger.info("Clicked semantic target: %s", semantic_target)
            return

        self._run_code_with_selectors(semantic_target, action="click")
        self._snapshot_cache = {"url": self.current_url, "text": "", "elements": [], "refs": []}
        logger.info("Clicked semantic target via selector fallback: %s", semantic_target)

    def type_text(self, semantic_target: str, value: str) -> None:
        tool_args = self._resolve_tool_args(semantic_target)
        if tool_args is not None:
            tool_args["text"] = value
            self._call_tool("browser_type", tool_args)
            self._snapshot_cache = {"url": self.current_url, "text": "", "elements": [], "refs": []}
            logger.info("Typed into %s value length=%s", semantic_target, len(value))
            return

        self._run_code_with_selectors(semantic_target, action="fill", value=value)
        self._snapshot_cache = {"url": self.current_url, "text": "", "elements": [], "refs": []}
        logger.info("Typed into %s via selector fallback value length=%s", semantic_target, len(value))

    def resize(self, width: int = 1440, height: int = 1000) -> None:
        try:
            self._call_tool("browser_resize", {"width": width, "height": height})
            logger.info("Browser viewport resized to %sx%s", width, height)
        except Exception as exc:  # pragma: no cover - depends on MCP server tool support
            logger.warning("Browser viewport resize skipped: %s", exc)

    def take_screenshot(
        self,
        name: str,
        *,
        full_page: bool = False,
        width: int = 1440,
        height: int = 1000,
    ) -> Path:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("_") or "screenshot"
        path = Path("logs/screenshots") / f"{safe_name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.resize(width=width, height=height)

        payload = self._call_tool("browser_take_screenshot", {"type": "png", "fullPage": full_page})
        image_bytes = self._extract_image_bytes(payload)
        if image_bytes:
            path.write_bytes(image_bytes)
            self._warn_if_low_quality_screenshot(path, image_bytes)
            logger.info("Screenshot saved: %s", path)
            return path

        self._call_tool(
            "browser_take_screenshot",
            {"filename": path.as_posix(), "type": "png", "fullPage": full_page},
        )
        self._warn_if_low_quality_screenshot(path, path.read_bytes() if path.exists() else b"")
        logger.info("Screenshot requested from MCP server: %s", path)
        return path


    def click_bus_offer(self, offer: dict[str, Any]) -> None:
        """Click the Book Ticket control that matches a ranked Shohoz bus offer."""
        booking_ref = str(offer.get("booking_ref") or "").strip()
        if booking_ref:
            try:
                self.click(booking_ref)
                return
            except Exception as exc:
                logger.warning("Saved booking ref %s was not clickable; falling back to offer text match: %s", booking_ref, exc)

        target = {
            "operator": str(offer.get("title") or "").lower(),
            "departure": str(offer.get("departure_time") or "").lower(),
            "fare": str(offer.get("total_usd") or "").replace(".0", ""),
        }
        script = f"""
async (page) => {{
  const target = {json.dumps(target)};
  const buttons = page.locator('button, a').filter({{ hasText: /book\s*ticket/i }});
  const count = await buttons.count();
  for (let i = 0; i < count; i++) {{
    const button = buttons.nth(i);
    const matched = await button.evaluate((el, target) => {{
      let node = el;
      for (let depth = 0; node && depth < 9; depth++, node = node.parentElement) {{
        const text = (node.innerText || '').toLowerCase();
        const operatorOk = !target.operator || text.includes(target.operator);
        const departureOk = !target.departure || text.includes(target.departure);
        const fareOk = !target.fare || text.includes(target.fare);
        if (operatorOk && departureOk && fareOk) return true;
      }}
      return false;
    }}, target);
    if (matched) {{
      await button.click();
      return {{ clicked: true, index: i }};
    }}
  }}
  throw new Error(`No matching Book Ticket button found for ${{target.operator}} ${{target.departure}} ${{target.fare}}`);
}}
""".strip()
        self._call_tool("browser_run_code", {"code": script})
        self._snapshot_cache = {"url": self.current_url, "text": "", "elements": [], "refs": []}

    def current_page_url(self) -> str:
        """Return the active page URL from the browser, if available."""
        payload = self._call_tool("browser_run_code", {"code": "async (page) => page.url()"})
        for key in ("text", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().strip('"')
        for item in payload.get("content", []):
            value = item.get("text") if isinstance(item, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip().strip('"')
        return self.current_url or ""

    def close(self) -> None:
        if self._loop is None:
            return

        if self._owner_task is not None:
            try:
                self._run_async(self._disconnect_async())
            except Exception as exc:  # pragma: no cover - cleanup best effort
                logger.warning("Failed to close MCP browser session cleanly: %s", exc)

        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=2)

        if self._loop.is_running():
            logger.warning("Async event loop did not stop before close; leaving daemon thread to exit.")
        else:
            self._loop.close()

        self.connected = False
        self._loop = None
        self._loop_thread = None

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.close()
        except Exception:
            pass

    async def _connect_async(self) -> None:
        if self._session is not None:
            return

        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._shutdown_event = asyncio.Event()
        self._owner_task = asyncio.create_task(self._session_owner(ready, self._shutdown_event))
        try:
            await ready
        except BaseException:
            self._shutdown_event.set()
            if self._owner_task is not None:
                self._owner_task.cancel()
                with suppress(Exception, asyncio.CancelledError):
                    await self._owner_task
            self._owner_task = None
            self._shutdown_event = None
            self._session = None
            self._available_tools.clear()
            raise

    async def _session_owner(
        self,
        ready: asyncio.Future[None],
        shutdown_event: asyncio.Event,
    ) -> None:
        client_session_cls, streamable_http_client = self._load_mcp_client()
        try:
            async with streamable_http_client(settings.mcp_server_url) as (read_stream, write_stream, _):
                async with client_session_cls(read_stream, write_stream) as session:
                    await session.initialize()
                    self._available_tools = await self._list_tools(session)
                    self._session = session
                    if not ready.done():
                        ready.set_result(None)
                    await shutdown_event.wait()
        except Exception:
            if not ready.done():
                ready.set_exception(RuntimeError(f"Unable to initialize MCP browser session at {settings.mcp_server_url}"))
            raise
        finally:
            self._session = None
            self._available_tools.clear()

    async def _disconnect_async(self) -> None:
        if self._shutdown_event is not None:
            self._shutdown_event.set()
        if self._owner_task is not None:
            await self._owner_task
        self._owner_task = None
        self._shutdown_event = None
        self._session = None
        self._available_tools.clear()
        self._snapshot_cache = {"url": self.current_url, "text": "", "elements": [], "refs": []}

    async def _list_tools(self, session: Any) -> set[str]:
        response = await session.list_tools()
        tools = getattr(response, "tools", []) or []
        return {getattr(tool, "name", "") for tool in tools if getattr(tool, "name", "")}

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            self.connect()

        last_error: Exception | None = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                payload = self._run_async(self._call_tool_async(tool_name, arguments))
                return self._coerce_payload(payload)
            except Exception as exc:  # pragma: no cover - exercised in integration
                last_error = exc
                logger.warning(
                    "Tool %s failed on attempt %s/%s: %s",
                    tool_name,
                    attempt,
                    settings.max_retries,
                    exc,
                )
                self.connected = False
                try:
                    self._run_async(self._disconnect_async())
                except Exception:
                    pass
                if attempt < settings.max_retries:
                    time.sleep(1)
                    self.connect()

        raise RuntimeError(f"MCP tool call failed: {tool_name}") from last_error

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("Browser session is not connected.")

        if self._available_tools and tool_name not in self._available_tools:
            raise RuntimeError(f"Tool {tool_name} is not exposed by the MCP server.")

        try:
            return await self._session.call_tool(tool_name, arguments=arguments)
        except TypeError:
            return await self._session.call_tool(tool_name, arguments)

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, args=(self._loop,), daemon=True)
        self._loop_thread.start()

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _run_async(self, coroutine: Any) -> Any:
        if self._loop is None:
            raise RuntimeError("Async event loop has not been initialized.")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=settings.mcp_command_timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            with suppress(FutureCancelledError, FutureTimeoutError):
                future.result(timeout=2)
            raise

    @staticmethod
    def _load_mcp_client() -> tuple[Any, Any]:
        try:
            from mcp import ClientSession
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("The Python MCP SDK is not installed. Run `pip install -r requirements.txt`.") from exc

        try:
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            try:
                from mcp.client.streamablehttp_client import streamablehttp_client as streamable_http_client
            except ImportError as exc:  # pragma: no cover - depends on SDK version
                raise RuntimeError("The installed MCP SDK does not expose a streamable HTTP client.") from exc

        return ClientSession, streamable_http_client

    def _load_selector_map(self) -> dict[str, list[str]]:
        selector_path = Path(__file__).with_name("selectors.yaml")
        if not selector_path.exists():
            return {}

        raw = yaml.safe_load(selector_path.read_text(encoding="utf-8")) or {}
        return {key: [str(item) for item in values] for key, values in raw.items() if isinstance(values, list)}

    def _resolve_tool_args(self, semantic_target: str) -> dict[str, str] | None:
        refs = self._snapshot_cache.get("refs", [])
        if not refs:
            refs = self.snapshot().get("refs", [])

        candidates = [semantic_target, *self._selector_aliases(semantic_target)]
        for candidate in candidates:
            normalized_candidate = self._normalize(candidate)
            for ref_entry in refs:
                description = ref_entry["description"]
                ref = ref_entry["ref"]
                normalized_description = self._normalize(description)
                if normalized_candidate == ref or normalized_candidate == normalized_description:
                    return {"element": description, "ref": ref}
                if normalized_candidate and normalized_candidate in normalized_description:
                    return {"element": description, "ref": ref}

        return None

    def _selector_aliases(self, semantic_target: str) -> list[str]:
        selectors = self._selector_map.get(semantic_target, [])
        aliases: list[str] = []
        for selector in selectors:
            has_text_match = re.search(r':has-text\("([^"]+)"\)', selector)
            if has_text_match:
                aliases.append(has_text_match.group(1))
            name_match = re.search(r'\[name="([^"]+)"\]', selector)
            if name_match:
                aliases.append(name_match.group(1))
        return aliases

    def _run_code_with_selectors(self, semantic_target: str, action: str, value: str = "") -> None:
        selectors = self._selector_map.get(semantic_target)
        if not selectors:
            raise RuntimeError(f"No MCP ref or selector mapping found for semantic target: {semantic_target}")

        quoted_selectors = ", ".join(repr(selector) for selector in selectors)
        if action == "click":
            script = f"""
async (page) => {{
  const selectors = [{quoted_selectors}];
  for (const selector of selectors) {{
    const locator = page.locator(selector).first();
    if (await locator.count()) {{
      await locator.click();
      return selector;
    }}
  }}
  throw new Error("Unable to click semantic target: {semantic_target}");
}}
""".strip()
        else:
            script = f"""
async (page) => {{
  const selectors = [{quoted_selectors}];
  for (const selector of selectors) {{
    const locator = page.locator(selector).first();
    if (await locator.count()) {{
      await locator.fill({value!r});
      return selector;
    }}
  }}
  throw new Error("Unable to fill semantic target: {semantic_target}");
}}
""".strip()

        self._call_tool("browser_run_code", {"code": script})

    @classmethod
    def _extract_refs(cls, snapshot_text: str) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        for line in snapshot_text.splitlines():
            ref_match = cls._REF_PATTERN.search(line)
            if not ref_match:
                continue
            description = cls._REF_PATTERN.sub("", line).strip(" -\t")
            if description:
                refs.append({"ref": ref_match.group("ref"), "description": description})
        return refs

    def _extract_snapshot_text(self, payload: dict[str, Any]) -> str:
        if not payload:
            return ""

        if isinstance(payload.get("structured_content"), dict):
            structured = payload["structured_content"]
            for key in ("text", "snapshot", "page_text", "markdown"):
                value = structured.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        for key in ("text", "snapshot", "page_text", "markdown"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value

        content = payload.get("content", [])
        text_chunks = [item["text"] for item in content if isinstance(item, dict) and item.get("text")]
        return "\n".join(text_chunks).strip()

    def _extract_image_bytes(self, payload: dict[str, Any]) -> bytes | None:
        content = payload.get("content", [])
        for item in content:
            data = item.get("data") if isinstance(item, dict) else None
            if not data:
                continue
            try:
                return base64.b64decode(data)
            except Exception:
                continue
        return None

    def _warn_if_low_quality_screenshot(self, path: Path, image_bytes: bytes) -> None:
        dimensions = self._png_dimensions(image_bytes)
        if dimensions is None:
            return

        width, height = dimensions
        if width < 600 or height < 400:
            logger.warning(
                "Screenshot %s has small dimensions %sx%s; dashboard preview may be limited.",
                path,
                width,
                height,
            )

    @staticmethod
    def _png_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
        if len(image_bytes) < 24 or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        try:
            return struct.unpack(">II", image_bytes[16:24])
        except struct.error:
            return None

    def _coerce_payload(self, result: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {}

        structured_content = getattr(result, "structuredContent", None)
        if structured_content is None:
            structured_content = getattr(result, "structured_content", None)
        if isinstance(structured_content, dict):
            payload["structured_content"] = structured_content

        content = getattr(result, "content", None)
        normalized_content: list[dict[str, Any]] = []
        if content:
            for item in content:
                item_type = getattr(item, "type", None) or item.__class__.__name__.replace("Content", "").lower()
                text = getattr(item, "text", None)
                data = getattr(item, "data", None)
                entry = {"type": item_type}
                if text is not None:
                    entry["text"] = text
                if data is not None:
                    entry["data"] = data
                normalized_content.append(entry)
            payload["content"] = normalized_content

        if isinstance(result, dict):
            payload.update(result)
        elif hasattr(result, "model_dump"):
            model_payload = result.model_dump()
            if isinstance(model_payload, dict):
                payload.update(model_payload)

        return payload

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.lower().split())
