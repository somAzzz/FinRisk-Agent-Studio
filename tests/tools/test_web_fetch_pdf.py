from unittest.mock import AsyncMock

import httpx
import pytest

from src.annual_reports import documents
from src.tools import web_fetch


@pytest.mark.parametrize("readable", [True, False])
async def test_pdf_fetch_returns_physical_page_text_or_a_parse_error(monkeypatch, readable):
    url = "https://93.184.216.34/annual.pdf"
    response = httpx.Response(200, content=b"%PDF-1.7", headers={"Content-Type": "application/octet-stream"})
    client = AsyncMock()
    client.get.return_value = response
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)

    def extract(data, source):
        assert (data, source) == (response.content, url)
        if not readable:
            raise documents.DocumentError("Unreadable page")
        return documents.Document(url, "test", [documents.Page(2, "1", "Quarterly sales", "native")])

    monkeypatch.setattr(documents, "extract", extract)
    result = await web_fetch.web_fetch(url)
    if readable:
        assert result.status == "success"
        assert result.content == "[PDF page 2]\nQuarterly sales"
    else:
        assert result.status == "failed"
        assert result.error_code == "PARSE_ERROR"
        assert not result.content
