from __future__ import annotations

from unittest.mock import patch

import main as entrypoint


def test_api_command_starts_canonical_app() -> None:
    with patch("uvicorn.run") as run:
        result = entrypoint.main(
            ["api", "--host", "0.0.0.0", "--port", "9000"]
        )
    assert result == 0
    run.assert_called_once_with(
        "src.api.main:app",
        host="0.0.0.0",
        port=9000,
        reload=False,
    )


def test_workflow_command_forwards_arguments() -> None:
    with patch("src.workflows.finrisk_workflow.main", return_value=0) as run:
        result = entrypoint.main(
            ["workflow", "--ticker", "AAPL", "--analysis-goal", "risks"]
        )
    assert result == 0
    run.assert_called_once_with(
        ["--ticker", "AAPL", "--analysis-goal", "risks"]
    )
