from agentstockbenchmark.stage1.migration import strategy_slug_from_cache_name


def test_strategy_slug_from_cache_name_removes_only_version_suffix():
    assert (
        strategy_slug_from_cache_name("OpenAI__O4_mini__LinearNeutral_202605")
        == "OpenAI__O4_mini__LinearNeutral"
    )
    assert (
        strategy_slug_from_cache_name("OpenAI__GPT5_3_Codex__LinearNeutral_v16")
        == "OpenAI__GPT5_3_Codex__LinearNeutral"
    )
