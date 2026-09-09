from extraction.border_token_pruner import prune_border_tokens


def test_pruner_keeps_raw_and_removes_field_label():
    result = prune_border_tokens("Tờ bản đồ số: 3", field="to_ban_do")
    assert result["raw_text"] == "Tờ bản đồ số: 3"
    assert result["pruned_text"] == "3"
    assert result["removed_tokens"]


def test_pruner_is_conservative_for_owner_name():
    result = prune_border_tokens("Bà: Nguyễn Thị Hằng")
    assert result["raw_text"] == "Bà: Nguyễn Thị Hằng"
    assert result["pruned_text"] == "Bà: Nguyễn Thị Hằng"


def test_area_unit_is_removed_only_for_area_field():
    result = prune_border_tokens("48.30 m²", field="dien_tich")
    assert result["pruned_text"] == "48.30"
