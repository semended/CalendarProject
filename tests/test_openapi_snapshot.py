"""OpenAPI snapshot — фиксируем контракт API, чтобы случайные изменения
сигнатуры (новый параметр, переименованное поле response_model) ловились
в PR. Если изменение намеренное — обнови snapshot:

    pytest tests/test_openapi_snapshot.py --snapshot-update

Хранится сериализованный JSON в tests/snapshots/openapi.json.
"""
import json
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi.json"


def _normalize(spec: dict) -> dict:
    """Нормализуем рандом: openapi-version и порядок ключей и т.п.,
    чтобы snapshot был детерминирован между прогонами."""
    return json.loads(json.dumps(spec, sort_keys=True, ensure_ascii=False))


@pytest.fixture
def snapshot_update(request):
    return request.config.getoption("--snapshot-update", default=False)


def test_openapi_snapshot_matches(client, snapshot_update):
    r = client.get("/openapi.json")
    assert r.status_code == 200, r.text
    current = _normalize(r.json())

    if snapshot_update or not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps(current, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        if not snapshot_update:
            pytest.skip("Snapshot создан с нуля, перезапусти тесты")
        return

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    expected = _normalize(expected)

    if expected != current:
        # Краткий diff: какие пути появились/исчезли — самое полезное в
        # PR-ревью. Полный diff виден через --snapshot-update + git diff.
        old_paths = set(expected.get("paths", {}).keys())
        new_paths = set(current.get("paths", {}).keys())
        added = sorted(new_paths - old_paths)
        removed = sorted(old_paths - new_paths)
        msg_lines = ["OpenAPI контракт изменился."]
        if added:
            msg_lines.append(f"Добавлены пути: {added}")
        if removed:
            msg_lines.append(f"Удалены пути:  {removed}")
        msg_lines.append(
            "Если изменение намеренное — pytest tests/test_openapi_snapshot.py "
            "--snapshot-update и закоммить snapshot."
        )
        pytest.fail("\n".join(msg_lines))
