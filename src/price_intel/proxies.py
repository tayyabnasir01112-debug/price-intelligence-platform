from collections.abc import Iterator
from itertools import cycle

from price_intel.schemas import ProxyConfig


class RotationPool:
    def __init__(self, values: list[str]):
        self._values = [value for value in values if value]
        self._iterator: Iterator[str] | None = cycle(self._values) if self._values else None

    def next(self) -> str | None:
        if self._iterator is None:
            return None
        return next(self._iterator)


class ProxyRotation:
    def __init__(self, proxies: list[ProxyConfig]):
        self._iterator: Iterator[ProxyConfig] | None = cycle(proxies) if proxies else None

    def next_httpx_proxy(self) -> str | None:
        if self._iterator is None:
            return None
        return next(self._iterator).url

    def next_playwright_proxy(self) -> dict[str, str] | None:
        if self._iterator is None:
            return None
        proxy = next(self._iterator)
        data = {"server": proxy.url}
        if proxy.username:
            data["username"] = proxy.username
        if proxy.password:
            data["password"] = proxy.password
        return data
