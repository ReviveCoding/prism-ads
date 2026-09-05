from __future__ import annotations

from prism_ads.pipeline.__main__ import main


def test_status_command(capsys: object) -> None:
    assert main(["status"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"project": "PRISM-Ads"' in captured.out
    assert '"controller_verification"' in captured.out
