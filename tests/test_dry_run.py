from app.services.dry_run import simulate


def test_skips_http_side_effects():
    out = simulate(
        [{"id": "a", "type": "transform"}, {"id": "b", "type": "http_request"}],
        [{"source": "a", "target": "b"}],
    )
    assert out["safe"] is True
    assert "b" in out["skipped_side_effects"]
