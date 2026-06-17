import httpx

from price_intel.extractors import HttpExtractor, parse_html
from price_intel.schemas import ExtractorKind, SelectorSpec, TargetConfig
from price_intel.settings import Settings


def target() -> TargetConfig:
    return TargetConfig(
        name="product",
        url="https://example.com/item",
        extractor=ExtractorKind.HTTP,
        selectors=[
            SelectorSpec(name="price", css=".price", required=True),
            SelectorSpec(name="missing", css=".missing", required=False),
            SelectorSpec(name="links", css="a", attr="href", many=True),
        ],
    )


def test_parse_html_handles_missing_optional_selector() -> None:
    result = parse_html("<div class='price'>$10</div><a href='/x'>x</a>", target())

    assert result.success is True
    assert result.values["price"] == "$10"
    assert result.values["missing"] is None
    assert result.values["links"] == ["/x"]


def test_parse_html_reports_missing_required_selector() -> None:
    cfg = target().model_copy(
        update={"selectors": [SelectorSpec(name="price", css=".nope", required=True)]}
    )
    result = parse_html("<div></div>", cfg)

    assert result.success is False
    assert "required selector missing" in result.errors[0]


async def test_http_extractor_uses_mock_transport() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<span class='price'>$42</span>", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        extractor = HttpExtractor(client, Settings())
        result = await extractor.extract(target())

    assert result.success is True
    assert result.values["price"] == "$42"
