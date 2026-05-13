from app.services.retrieval import reciprocal_rank_fusion


def test_rrf_orders_by_overlap():
    a = ["x", "y", "z"]
    b = ["y", "x", "w"]
    fused = reciprocal_rank_fusion([a, b])
    assert fused[0] in {"x", "y"}
