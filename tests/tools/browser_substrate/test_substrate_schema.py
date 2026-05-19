def test_browser_substrate_config_defaults_and_aliases():
    from ava.forks.config.schema import BrowserSubstrateConfig, ToolsConfig

    c = BrowserSubstrateConfig()
    assert c.enabled is False
    assert c.mcp_server == "playwright_daily"
    assert c.network_cache_max == 500
    assert c.console_cache_max == 200
    assert c.errors_cache_max == 100
    assert c.body_max_bytes == 65536
    assert c.adapter_dir == "~/.ava/browser-sites"

    c2 = BrowserSubstrateConfig.model_validate({
        "enabled": True,
        "mcpServer": "playwright_alt",
        "networkCacheMax": 100,
        "bodyMaxBytes": 8192,
        "adapterDir": "/tmp/sites",
    })
    assert c2.mcp_server == "playwright_alt"
    assert c2.network_cache_max == 100
    assert c2.body_max_bytes == 8192
    assert c2.adapter_dir == "/tmp/sites"

    t = ToolsConfig()
    assert t.browser_substrate.enabled is False

    dumped = t.model_dump(by_alias=True)
    assert "browserSubstrate" in dumped
    assert dumped["browserSubstrate"]["mcpServer"] == "playwright_daily"
    assert dumped["browserSubstrate"]["networkCacheMax"] == 500

    t2 = ToolsConfig.model_validate(dumped)
    assert t2.browser_substrate.mcp_server == "playwright_daily"
