import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
from bs4 import BeautifulSoup

from price_intel.proxies import ProxyRotation, RotationPool
from price_intel.schemas import ExtractorKind, SelectorSpec, TargetConfig
from price_intel.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionResult:
    target_name: str
    url: str
    success: bool
    values: dict[str, Any]
    errors: list[str]
    raw_excerpt: str | None = None


class Extractor(Protocol):
    async def extract(self, target: TargetConfig) -> ExtractionResult:
        raise NotImplementedError


def _extract_text_or_attr(element: Any, selector: SelectorSpec) -> str | None:
    if element is None:
        return None
    if selector.attr:
        value = element.get(selector.attr)
        return str(value).strip() if value is not None else None
    return cast(str, element.get_text(" ", strip=True))


def parse_html(html: str, target: TargetConfig) -> ExtractionResult:
    soup = BeautifulSoup(html, "html.parser")
    values: dict[str, Any] = {}
    errors: list[str] = []

    for selector in target.selectors:
        if selector.many:
            found = [_extract_text_or_attr(item, selector) for item in soup.select(selector.css)]
            cleaned = [item for item in found if item]
            values[selector.name] = cleaned
            if selector.required and not cleaned:
                errors.append(f"required selector returned no values: {selector.name}")
        else:
            item = soup.select_one(selector.css)
            value = _extract_text_or_attr(item, selector)
            values[selector.name] = value
            if selector.required and value is None:
                errors.append(f"required selector missing: {selector.name}")

    return ExtractionResult(
        target_name=target.name,
        url=str(target.url),
        success=not errors,
        values=values,
        errors=errors,
        raw_excerpt=html[:2000],
    )


class HttpExtractor:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self._client = client
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_http_concurrency)

    async def extract(self, target: TargetConfig) -> ExtractionResult:
        timeout = target.timeout_seconds or self._settings.request_timeout_seconds
        user_agents = RotationPool(target.user_agents)
        proxy = ProxyRotation(target.proxies).next_httpx_proxy()
        headers = dict(target.headers)
        if agent := user_agents.next():
            headers["User-Agent"] = agent

        async with self._semaphore:
            try:
                if proxy:
                    async with httpx.AsyncClient(proxy=proxy) as proxy_client:
                        response = await proxy_client.get(
                            str(target.url),
                            headers=headers,
                            timeout=timeout,
                            follow_redirects=True,
                        )
                else:
                    response = await self._client.get(
                        str(target.url),
                        headers=headers,
                        timeout=timeout,
                        follow_redirects=True,
                    )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                return ExtractionResult(
                    target_name=target.name,
                    url=str(target.url),
                    success=False,
                    values={},
                    errors=[str(exc)],
                )
        return parse_html(response.text, target)


class BrowserPool:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_browser_contexts)
        self._playwright: Any | None = None
        self._browser: Any | None = None

    async def start(self) -> None:
        if self._browser is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def extract(self, target: TargetConfig) -> ExtractionResult:
        await self.start()
        assert self._browser is not None

        proxy = ProxyRotation(target.proxies).next_playwright_proxy()
        context_kwargs: dict[str, Any] = {}
        if proxy:
            context_kwargs["proxy"] = proxy
        if target.user_agents:
            context_kwargs["user_agent"] = target.user_agents[0]

        async with self._semaphore:
            context = await self._browser.new_context(**context_kwargs)
            page = await context.new_page()
            try:
                await page.goto(
                    str(target.url),
                    wait_until="domcontentloaded",
                    timeout=int(
                        (target.timeout_seconds or self._settings.request_timeout_seconds) * 1000
                    ),
                )
                if target.wait_for_selector:
                    await page.wait_for_selector(target.wait_for_selector, timeout=5000)
                values: dict[str, Any] = {}
                errors: list[str] = []
                for selector in target.selectors:
                    if selector.many:
                        elements = await page.query_selector_all(selector.css)
                        values[selector.name] = []
                        for element in elements:
                            values[selector.name].append(
                                await self._read_browser_element(element, selector)
                            )
                        values[selector.name] = [value for value in values[selector.name] if value]
                        if selector.required and not values[selector.name]:
                            errors.append(f"required selector returned no values: {selector.name}")
                    else:
                        element = await page.query_selector(selector.css)
                        value = await self._read_browser_element(element, selector)
                        values[selector.name] = value
                        if selector.required and value is None:
                            errors.append(f"required selector missing: {selector.name}")
                html = await page.content()
                return ExtractionResult(
                    target_name=target.name,
                    url=str(target.url),
                    success=not errors,
                    values=values,
                    errors=errors,
                    raw_excerpt=html[:2000],
                )
            except Exception as exc:
                logger.exception(
                    "browser extraction failed",
                    extra={"price_intel_target": target.name},
                )
                return ExtractionResult(
                    target_name=target.name,
                    url=str(target.url),
                    success=False,
                    values={},
                    errors=[str(exc)],
                )
            finally:
                await context.close()

    @staticmethod
    async def _read_browser_element(element: Any, selector: SelectorSpec) -> str | None:
        if element is None:
            return None
        if selector.attr:
            value = await element.get_attribute(selector.attr)
            return value.strip() if value else None
        text = await element.text_content()
        return text.strip() if text else None


class ExtractorRegistry:
    def __init__(self, http_extractor: HttpExtractor, browser_pool: BrowserPool):
        self._http = http_extractor
        self._browser = browser_pool

    def get(self, kind: ExtractorKind) -> Extractor:
        if kind == ExtractorKind.HTTP:
            return self._http
        if kind == ExtractorKind.BROWSER:
            return self._browser
        raise ValueError(f"unsupported extractor: {kind}")

    async def stop(self) -> None:
        await self._browser.stop()
