from src.api.openapi import DEFAULT_PATH, main, openapi_schema, render


def test_frontend_schema_is_up_to_date():
    """La web genera sus tipos a partir de este fichero: si la API cambia, hay que regenerarlo."""
    assert DEFAULT_PATH.read_text(encoding="utf-8") == render(openapi_schema()), (
        "frontend/src/api/openapi.json está desactualizado: ejecuta make api-types"
    )


def test_export_to_another_path(tmp_path):
    path = tmp_path / "openapi.json"
    main([str(path)])
    assert path.read_text(encoding="utf-8") == render(openapi_schema())
