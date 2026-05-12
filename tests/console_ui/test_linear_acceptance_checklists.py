from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def assert_contains_all(source: str, needles: list[str]) -> None:
    missing = [needle for needle in needles if needle not in source]
    assert missing == []


def test_ava5_streaming_checklist_has_end_to_end_tested_contract() -> None:
    routes = read("ava/console/routes/chat_routes.py")
    service = read("ava/console/services/chat_service.py")
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    message_area = read("console-ui/src/pages/ChatPage/MessageArea.tsx")
    chat_service_tests = read("tests/console/test_chat_service.py")
    chat_route_tests = read("tests/console/test_chat_routes.py")

    assert_contains_all(
        routes,
        [
            "async def on_stream(chunk: str):",
            'await _dispatch_listener_event(chunk, event_type="progress")',
            "async def on_stream_end",
            '"stream_end"',
            'await _dispatch_listener_event(response, event_type="complete")',
        ],
    )
    assert_contains_all(service, ["on_stream=on_stream", "on_stream_end=on_stream_end"])
    assert_contains_all(
        chat_page,
        [
            "appendInFlightAssistantChunk(prev, data.content)",
            "applyInFlightStreamEnd(prev, !!data.resuming)",
            "finalizeConsoleInFlight()",
            "setTransportStatus('error')",
            "SEND_WATCHDOG_MS",
        ],
    )
    assert_contains_all(message_area, ["isNearBottom", "bottomRef.current?.scrollIntoView"])
    assert "test_send_message_passes_on_stream_to_agent_loop" in chat_service_tests
    assert "test_stream_end_payload_preserves_resuming_flag" in chat_route_tests


def test_ava6_session_switch_and_scroll_checklist_is_covered() -> None:
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    message_area = read("console-ui/src/pages/ChatPage/MessageArea.tsx")
    service = read("ava/console/services/chat_service.py")

    assert_contains_all(
        chat_page,
        [
            "pickConversationId",
            "conversations[0].conversation_id",
            "forceActiveConversation",
            "loadSessionMessagesWithMetaRef.current",
        ],
    )
    assert_contains_all(
        service,
        [
            "active_conversation_id = self._resolve_active_conversation_id",
            "conversations.sort",
            "item[\"is_active\"]",
        ],
    )
    assert_contains_all(
        message_area,
        [
            "isInitialScroll.current",
            "bottomRef.current.scrollIntoView({ behavior: 'instant' })",
            "isNearBottom",
            "setShowScrollDown(!isAtBottom)",
            "isInitialScroll.current = true",
        ],
    )


def test_ava7_trace_and_deep_link_checklist_is_covered() -> None:
    db = read("ava/storage/database.py")
    routes = read("ava/console/routes/chat_routes.py")
    service = read("ava/console/services/chat_service.py")
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    message_area = read("console-ui/src/pages/ChatPage/MessageArea.tsx")
    turn_group = read("console-ui/src/pages/ChatPage/TurnGroup.tsx")
    redirects = read("console-ui/src/router/redirect-matrix.ts")
    chat_tests = read("tests/console/test_chat_service.py")
    guardrail_tests = read("tests/guardrails/test_ava8_decoupling_boundary.py")
    route_tests = read("tests/console/test_chat_routes.py")

    assert_contains_all(
        db,
        [
            "ALTER TABLE session_messages ADD COLUMN trace_id TEXT DEFAULT ''",
            "CREATE INDEX IF NOT EXISTS idx_msg_trace ON session_messages(trace_id)",
        ],
    )
    assert_contains_all(
        routes,
        [
            "trace_id: str | None = Query",
            "return svc.get_messages_by_trace_id(trace_id)",
            "session_key or trace_id is required",
        ],
    )
    assert_contains_all(
        service,
        [
            "def get_messages_by_trace_id",
            "metadata[\"session_key\"]",
            "trace_id = row[\"trace_id\"]",
        ],
    )
    assert_contains_all(
        chat_page,
        [
            "deepLinkTraceId",
            "`/chat/messages?trace_id=${encodeURIComponent(deepLinkTraceIdVal)}`",
            "`/bg-tasks/${encodeURIComponent(deepLinkTaskIdVal)}`",
            "targetTraceId={deepLinkTraceId}",
        ],
    )
    assert_contains_all(
        message_area,
        [
            'querySelector(`[data-trace-id="${CSS.escape(targetTraceId)}"]`)',
            'querySelector(`[data-bg-task-id="${CSS.escape(targetTaskId)}"]`)',
        ],
    )
    assert 'data-trace-id={isTargetTrace ? targetTraceId : traceIds[0]}' in turn_group
    assert "rule.from === '/tokens' && params.has('trace_id')" in redirects
    assert "test_get_messages_by_trace_id_returns_session_metadata" in chat_tests
    assert "test_get_messages_accepts_trace_id_without_session_key" in route_tests


def test_ava8_nanobot_decoupling_epic_checklist_is_covered() -> None:
    app = read("ava/console/app.py")
    console_init = read("ava/console/__init__.py")
    storage_init = read("ava/storage/__init__.py")
    agent_commands = read("ava/agent/commands.py")
    direct_service = read("ava/console/services/direct_task_service.py")
    schema = read("ava/forks/config/schema.py")
    service = read("ava/console/services/chat_service.py")
    registry = read("ava/console/services/agent_registry_service.py")
    process_manager = read("ava/agents/process_manager.py")
    config_tests = read("tests/console/test_config_service.py")
    chat_tests = read("tests/console/test_chat_service.py")
    guardrail_tests = read("tests/guardrails/test_ava8_decoupling_boundary.py")

    forbidden_product_copy = [
        "Nanobot Console",
        "Web management console for Nanobot",
        "Web Console extension for nanobot",
        "Local SQLite storage layer for nanobot",
        "Nanobot commands",
        "Hi! I'm nanobot",
        "Nanobot Status",
        "carries nanobot",
    ]
    product_surface = "\n".join([app, console_init, storage_init, agent_commands, direct_service])
    for text in forbidden_product_copy:
        assert text not in product_surface

    assert_contains_all(
        registry,
        [
            "from ava.agents import default_agent_adapters",
            "self._adapters = list(adapters) if adapters is not None else default_agent_adapters()",
            "adapter.build_snapshot",
        ],
    )
    assert "class AgentProcessManager" in process_manager
    assert_contains_all(
        schema,
        [
            "class ConsoleConfig",
            "default_responder_agent_id: str = Field",
            "class NanobotConfig",
            "class Config(NanobotConfig)",
        ],
    )
    assert_contains_all(
        service,
        [
            "console-config.json",
            "defaultResponderAgentId",
            "def _default_responder_agent_id",
        ],
    )
    assert_contains_all(
        config_tests + chat_tests,
        [
            "test_console_config_projection_excludes_nanobot_sections",
            "test_backend_schema_names_console_and_nanobot_configs_separately",
            "test_create_session_defaults_to_console_default_responder",
        ],
    )
    assert "test_ava8_common_surface_nanobot_references_are_classified" in guardrail_tests


def test_ava9_legacy_route_migration_checklist_is_covered() -> None:
    redirects = read("console-ui/src/router/redirect-matrix.ts")
    app = read("console-ui/src/App.tsx")
    redirect_tests = read("tests/console_ui/test_redirect_matrix.py")

    assert_contains_all(
        redirects,
        [
            "{ from: '/agents', to: '/settings/agents-config' }",
            "{ from: '/config', to: '/settings/system/console' }",
            "{ from: '/memory', to: '/settings/agents-config/nanobot/memory' }",
            "{ from: '/persona', to: '/settings/agents-config/nanobot/persona' }",
            "{ from: '/skills', to: '/settings/tools/skills' }",
            "{ from: '/chat', to: '/', renameParams: { session_key: 'session_id' } }",
            "{ from: '/tasks', to: '/', defaults: { view: 'tasks', task_view: 'scheduled' } }",
            "{ from: '/bg-tasks', to: '/', defaults: { view: 'tasks', task_view: 'history' } }",
            "{ from: '/media', to: '/', defaults: { view: 'tasks', task_view: 'artifacts' } }",
            "params.toString()",
        ],
    )
    assert_contains_all(app, ["legacyRedirectMatrix.map", "resolveLegacyRedirect"])
    assert_contains_all(
        redirect_tests,
        [
            "test_legacy_redirect_matrix_covers_retired_routes",
            "test_task_overlay_redirects_use_parameterized_chat_route",
        ],
    )


def test_ava10_chat_control_plane_layout_and_read_only_checklist_is_covered() -> None:
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    message_area = read("console-ui/src/pages/ChatPage/MessageArea.tsx")
    sidebar = read("console-ui/src/pages/ChatPage/SessionSidebar.tsx")
    utils = read("console-ui/src/pages/ChatPage/utils.ts")
    hud = read("console-ui/src/pages/ChatPage/HudBar.tsx")
    layout = read("console-ui/src/components/layout/Layout.tsx")

    assert_contains_all(
        chat_page,
        [
            "const filteredSessions = sessions",
            "<TaskPreviewBar",
            "<SessionSidebar",
            "<MessageArea",
            "mobileSessionOpen",
            "isReadOnlyConversation",
            "只读模式 · 申请权限",
            "onParticipantsChange={handleParticipantsChange}",
        ],
    )
    assert "<SceneTabs" not in chat_page
    assert "ConversationConfigBar" not in chat_page
    assert_contains_all(
        message_area,
        [
            "<HudBar",
            "{isConsole && !isReadOnly && (",
            "onToggleSessionPanel",
            "<ChatHeader",
            "onParticipantsChange",
        ],
    )
    assert_contains_all(
        sidebar,
        [
            "getSessionTitle(s)",
            "getSessionParticipants(s)",
            "participantLabels.join(' / ')",
            "getAgentInitial(agentId)",
            "primaryConversation?.first_message_preview",
        ],
    )
    assert_contains_all(
        utils,
        [
            "export function getSessionTitle",
            "export function getSessionParticipants",
            "export function getAgentLabel",
            "export function getAgentInitial",
        ],
    )
    assert_contains_all(hud, ["Token", "Skills", "Artifacts", "Memory"])
    assert "MOCK SANDBOX" in layout


def test_ava12_hud_widget_checklist_is_covered() -> None:
    """spec §2.5：Chat HUD 渲染 4 静态 widget（Token / Skills / Artifacts / Memory）。

    P2 marketplace（HudWidgetRegistry / preferences / capability gating）由
    AVA-29 deferred 桶覆盖，本检查只断言 4 widget 的数据源与跳转目标。
    """
    hud = read("console-ui/src/pages/ChatPage/HudBar.tsx")
    models = read("ava/console/models.py")
    gateway_service = read("ava/console/services/gateway_service.py")
    gateway_tests = read("tests/console/test_gateway_service.py")

    assert_contains_all(
        hud,
        [
            "label: 'Token'",
            "label: 'Skills'",
            "label: 'Artifacts'",
            "label: 'Memory'",
            "api<{ skills: SkillSummary[] }>('/skills/list')",
            "setSkills(null)",
            "setSkillsOpen(false)",
            "grid min-w-80 grid-cols-1 gap-2 sm:grid-cols-2",
            "api<GatewayStatusData>('/gateway/status')",
            "memory_rss_bytes",
            "buildTokenStatsNavUrl({ sessionKey: session.key })",
            "navigate('/?view=tasks&task_view=artifacts')",
        ],
    )
    assert "buildHudWidgetInstances" not in hud
    assert "loadHudWidgetPreferences" not in hud
    assert "subscribeHudWidgetChanges" not in hud
    assert "performance as Performance" not in hud
    assert "usedJSHeapSize" not in hud
    assert "N/A" not in hud
    assert "memory_rss_bytes: int | None = None" in models
    assert "_current_process_rss_bytes()" in gateway_service
    assert "test_get_status_without_lifecycle" in gateway_tests
    assert "status.memory_rss_bytes" in gateway_tests


def test_ava13_settings_information_architecture_checklist_is_covered() -> None:
    settings = read("console-ui/src/pages/SettingsPage.tsx")
    app = read("console-ui/src/App.tsx")
    app_py = read("ava/console/app.py")
    routes_init = read("ava/console/routes/__init__.py")
    redirects = read("console-ui/src/router/redirect-matrix.ts")
    nav_items = read("console-ui/src/components/layout/navItems.ts")

    assert_contains_all(settings, ["Agents Config", "Statistics", "Tools", "Users", "System"])
    assert_contains_all(
        app,
        [
            'path="settings"',
            'path="agents-config"',
            'path="statistics"',
            'path="tools/skills"',
            'path="users" element={<ProtectedRoute allowedRoles={[\'admin\']}><UsersPage /></ProtectedRoute>}',
            'path="system/gateway"',
            'path="system/browser"',
            'path="system/console"',
        ],
    )
    assert_contains_all(redirects, ["/settings/agents-config", "/settings/statistics", "/settings/tools/skills"])
    assert "export const navItems: NavItem[] = [" in nav_items
    assert "label: 'Settings'" in nav_items
    for deferred_entry in [
        "/settings/inbox",
        "/settings/tools/workflows",
        "/settings/system/relay",
        "/settings/system/notifications",
        "/settings/system/hud-widgets",
    ]:
        assert deferred_entry not in settings
        assert deferred_entry not in app
    for deferred_route in ["inbox_routes", "relay_routes", "notification_routes", "collaboration_routes"]:
        assert deferred_route not in app_py
        assert deferred_route not in routes_init


def test_ava14_config_separation_checklist_is_covered() -> None:
    schema = read("ava/forks/config/schema.py")
    config_service = read("ava/console/services/config_service.py")
    config_page = read("console-ui/src/pages/ConfigPage/index.tsx")
    direct_service = read("ava/console/services/direct_task_service.py")
    config_tests = read("tests/console/test_config_service.py")
    direct_tests = read("tests/console/test_direct_task_service.py")

    assert_contains_all(
        schema,
        [
            "class ConsoleConfig(Base):",
            "class NanobotConfig(BaseSettings):",
            "class Config(NanobotConfig):",
            "agents: AgentsConfig",
            "providers: ProvidersConfig",
            "tools: ToolsConfig",
        ],
    )
    assert_contains_all(
        config_service,
        [
            '"nanobot-config.json": "config.json"',
            '"console-config.json": "console/console-config.json"',
            '"codex-config.toml": "console/agents/codex/config.toml"',
            '"claude-code-settings.json": "console/agents/claude_code/settings.json"',
            '"image-gen-config.json": "console/agents/image_gen/config.json"',
            "_read_console_config_projection",
        ],
    )
    assert_contains_all(
        config_page,
        [
            "type ConfigPageMode = 'nanobot' | 'console' | 'legacy' | 'codex' | 'claude_code' | 'image_gen'",
            "console: 'console-config.json'",
            "codex: 'codex-config.toml'",
            "claude_code: 'claude-code-settings.json'",
            "image_gen: 'image-gen-config.json'",
            "const AGENT_CONFIG_MODES = new Set<ConfigPageMode>(['nanobot', 'codex', 'claude_code', 'image_gen'])",
        ],
    )
    assert_contains_all(
        direct_service,
        ["_load_agent_config(\"codex\")", "_load_agent_config(\"claude_code\")", "_load_agent_config(\"image_gen\")"],
    )
    assert_contains_all(
        config_tests,
        [
            "test_console_config_projection_excludes_nanobot_sections",
            "test_console_config_persists_independently_after_first_write",
            "test_backend_schema_names_console_and_nanobot_configs_separately",
            "test_agent_specific_configs_are_separate_from_console_config",
        ],
    )
    assert_contains_all(
        direct_tests,
        [
            "test_submit_codex_direct_task_uses_agent_specific_config",
            "test_submit_claude_code_direct_task_uses_agent_specific_config",
        ],
    )


def test_ava15_skill_at_name_explicit_trigger_checklist_is_covered() -> None:
    input_page = read("console-ui/src/pages/ChatPage/ChatInput.tsx")
    hud = read("console-ui/src/pages/ChatPage/HudBar.tsx")
    routes = read("ava/console/routes/chat_routes.py")
    service = read("ava/console/services/chat_service.py")
    tests = read("tests/console_ui/test_linear_acceptance_checklists.py")

    assert_contains_all(
        input_page,
        [
            "skillSuggestions",
            "filterSkillSuggestions",
            "insertSkillTrigger",
            "@skill_name",
            "onSkillTriggerSelect",
        ],
    )
    assert_contains_all(hud, ["onSkillSelect", "insertSkillTrigger"])
    assert_contains_all(routes + service, ["parse_skill_trigger", "route_skill_trigger", "skill_name"])
    assert "test_ava15_skill_at_name_explicit_trigger_checklist_is_covered" in tests


def test_ava16_rbac_checklist_is_covered() -> None:
    auth = read("ava/console/auth.py")
    bg_routes = read("ava/console/routes/bg_task_routes.py")
    agent_routes = read("ava/console/routes/agent_routes.py")
    direct_routes = read("ava/console/routes/direct_task_routes.py")
    auth_store = read("console-ui/src/stores/auth.ts")
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    tests = read("tests/console/test_bg_task_routes.py") + read("tests/console/test_agent_routes.py") + read("tests/console/test_direct_task_routes.py")
    matrix = read("docs/rbac-capability-matrix.md")

    assert_contains_all(auth, ['READ_ROLES = ("admin", "editor", "viewer", "read_only", "mock_tester")', 'EDIT_ROLES = ("admin", "editor")'])
    assert "Depends(auth.require_role(*auth.EDIT_ROLES))" in bg_routes
    assert "Depends(auth.require_role(*auth.EDIT_ROLES))" in agent_routes
    assert 'Depends(auth.require_role("admin", "editor"))' in direct_routes
    assert_contains_all(auth_store, ["return role === 'admin' || role === 'editor'", "'read_only'", "'mock_tester'"])
    assert_contains_all(chat_page, ["canMutateChat = canEdit()", "只读模式 · 申请权限", "isReadOnlyConversation"])
    assert_contains_all(tests, ["viewer_response.status_code == 403", "mock_response.status_code == 403", "read_only_response.status_code == 403"])
    assert_contains_all(matrix, ["`read_only`", "`mock_tester`"])


def test_ava17_agent_detail_and_agent_config_checklist_is_covered() -> None:
    app = read("console-ui/src/App.tsx")
    settings = read("console-ui/src/pages/SettingsPage.tsx")
    dashboard = read("console-ui/src/pages/AgentDashboardPage.tsx")
    config_service = read("ava/console/services/config_service.py")
    direct_service = read("ava/console/services/direct_task_service.py")
    redirect_tests = read("tests/console_ui/test_redirect_matrix.py")

    assert_contains_all(
        app,
        [
            'path="agents-config/:agentKind"',
            'path="agents-config/codex/config"',
            'path="agents-config/claude-code/config"',
            'path="agents-config/image-gen/config"',
        ],
    )
    assert_contains_all(settings, ["Codex Config", "Claude Config", "Image Gen Config"])
    assert_contains_all(
        dashboard,
        [
            "ROUTE_AGENT_NAME",
            "function AgentDetail",
            "Configuration",
            "Docs & Instructions",
            "Actions",
            "Edit Config",
            "handleSubmitTask",
            "'/console/direct-tasks'",
        ],
    )
    assert_contains_all(config_service, ["codex-config.toml", "claude-code-settings.json", "image-gen-config.json"])
    assert "config_service=svc.config" in read("ava/console/routes/chat_routes.py")
    assert "_config_service" in direct_service
    assert "test_agent_detail_tabs_are_nested_under_settings_agents_config" in redirect_tests


def test_ava19_adapter_registry_checklist_is_covered() -> None:
    adapter = read("ava/agents/adapter.py")
    registry = read("ava/console/services/agent_registry_service.py")
    adapters_init = read("ava/agents/__init__.py")
    registry_tests = read("tests/console/test_agent_registry_service.py")

    assert_contains_all(
        adapter,
        [
            "class AgentAdapter(Protocol):",
            "def build_snapshot",
            "def matches",
            "def get_health_check",
        ],
    )
    assert_contains_all(
        registry,
        [
            "from ava.agents import default_agent_adapters",
            "self._adapters = list(adapters) if adapters is not None else default_agent_adapters()",
            "for adapter in self._adapters:",
            "adapter.build_snapshot",
        ],
    )
    assert_contains_all(adapters_init, ["NanobotAdapter()", "ClaudeCodeAdapter()", "CodexAdapter()", "ImageGenAdapter()"])
    assert_contains_all(
        registry_tests,
        [
            "class _DummyAdapter",
            "test_agent_registry_accepts_external_adapter",
            "test_agent_registry_cancels_tasks_for_external_adapter",
            "by_name[\"nanobot\"]",
            "by_name[\"codex\"]",
            "by_name[\"claude_code\"]",
            "by_name[\"image_gen\"]",
        ],
    )


def test_ava20_lan_access_checklist_is_covered() -> None:
    auth = read("ava/console/auth.py")
    app = read("ava/console/app.py")
    routes = read("ava/console/routes/lan_access_routes.py")
    service = read("ava/console/services/lan_access_service.py")
    console_patch = read("ava/patches/console_patch.py")
    settings = read("console-ui/src/pages/SettingsPage.tsx")
    frontend = read("console-ui/src/pages/LanAccessPage.tsx")
    app_tsx = read("console-ui/src/App.tsx")
    route_tests = read("tests/console/test_lan_access_routes.py")

    assert_contains_all(
        service,
        [
            "LAN_ACCESS_STATE_FILE = \"lan-access.json\"",
            "PAIRING_TTL_SECONDS = 5 * 60",
            "def resolve_console_bind_host",
            "return \"0.0.0.0\"",
            "return \"127.0.0.1\"",
            "def create_pairing_pin",
            "f\"{secrets.randbelow(1_000_000):06d}\"",
            "def pair_device",
            "\"role\": \"read_only\"",
            "\"capabilities\": [\"read\"]",
            "def revoke_device",
            "def validate_device_token",
            "def mark_device_seen",
        ],
    )
    assert_contains_all(
        auth,
        [
            "set_device_token_validator",
            "payload.get(\"kind\") == \"device\"",
            "request.state.device_id = payload.get(\"device_id\")",
        ],
    )
    assert_contains_all(
        routes,
        [
            "APIRouter(prefix=\"/api/lan-access\"",
            "@router.get(\"/status\")",
            "@router.put(\"/config\")",
            "@router.post(\"/pin\")",
            "@router.post(\"/pair\")",
            "@router.post(\"/devices/{device_id}/revoke\")",
            "auth.require_role(\"admin\")",
            "auth.set_session_cookie(response, payload[\"access_token\"])",
            "action=\"lan.device.pair\"",
            "action=\"lan.device.revoke\"",
        ],
    )
    assert_contains_all(
        app,
        [
            "lan_access: LanAccessService",
            "_install_device_audit_middleware",
            "action=\"lan.device_access\"",
            "auth.set_device_token_validator(real_services.lan_access.validate_device_token)",
            "app.include_router(lan_access_routes.router)",
        ],
    )
    assert "_install_lan_https_redirect_middleware(app)" not in app
    assert_contains_all(console_patch, ["resolve_console_bind_host(nanobot_dir, console_host)", "uvicorn.Config("])
    assert_contains_all(settings, ["'/settings/system/lan-access'", "label: 'LAN Access'", "allowedRoles: ['admin']"])
    assert_contains_all(app_tsx, ["import LanAccessPage", 'path="system/lan-access"', "allowedRoles={['admin']}"])
    assert_contains_all(
        frontend,
        [
            "api<LanStatus>('/lan-access/status')",
            "api<LanStatus>('/lan-access/config'",
            "api<PinResponse>('/lan-access/pin'",
            "api(`/lan-access/devices/${encodeURIComponent(deviceId)}/revoke`",
            "api<AuditResponse>('/audit/logs?action=lan.device_access&size=5')",
            "<ToggleSwitch",
            "status.lan_urls.map",
            "activeDevices.map",
            "audit.map",
        ],
    )
    for deferred_lan_ui in ["HTTPS", "mDNS", "PWA", "qr_svg", "pairing_url"]:
        assert deferred_lan_ui not in frontend
    assert_contains_all(
        route_tests,
        [
            "test_lan_access_defaults_to_localhost_and_admin_toggle_controls_bind_host",
            "test_lan_pairing_issues_read_only_device_token_and_revoke_invalidates_it",
            "test_lan_access_service_pin_is_single_use",
            "viewer_toggle.status_code == 403",
            "write_response.status_code == 403",
            "revoked_me.status_code == 401",
            "action=lan.device_access",
        ],
    )


def test_ava21_electron_shell_checklist_is_covered() -> None:
    root_package = read("package.json")
    electron_package = read("electron/package.json")
    main = read("electron/main.mjs")
    preload = read("electron/preload.cjs")
    wrapper = read("electron/bin/ava-core")
    build_script = read("electron/scripts/build.mjs")
    readme = read("electron/README.md") + read("README.md")
    desktop_tests = read("tests/desktop/test_electron_shell_contract.py")

    assert_contains_all(root_package, ["\"electron:build\": \"pnpm --dir electron build\"", "\"electron:dry-run\""])
    assert_contains_all(electron_package, ["\"main\": \"main.mjs\"", "\"build\": \"node scripts/build.mjs\"", "\"electron\": \"latest\""])
    assert_contains_all(
        main,
        [
            "spawn('/bin/bash', [wrapper]",
            "waitForAvaCore(config.healthEndpoint)",
            "/api/gateway/health",
            "mainWindow.loadURL(config.coreEndpoint)",
            "child.kill('SIGTERM')",
            "child.kill('SIGKILL')",
            "contextIsolation: true",
            "nodeIntegration: false",
            "sandbox: true",
        ],
    )
    assert_contains_all(
        preload,
        [
            "selectDirectory",
            "openPath",
            "getAppConfig",
            "getCoreEndpoint",
            "getAuthToken",
            "showNotification",
        ],
    )
    assert_contains_all(wrapper, ["scripts/start-ava.sh gateway", "trap shutdown INT TERM", "wait \"${core_pid}\""])
    assert_contains_all(build_script, ["--dry-run", "AVA Electron dry-run passed", "electron-packager", "--platform=darwin"])
    assert_contains_all(readme, ["pnpm electron:build", "pnpm electron:dry-run", "open electron/dist/Ava-darwin-arm64/Ava.app"])
    assert_contains_all(
        desktop_tests,
        [
            "test_electron_main_starts_healthchecks_and_stops_ava_core",
            "test_preload_exposes_only_p1b_native_whitelist",
            "test_electron_dry_run_build_script_executes",
        ],
    )


def test_ava22_workflow_foundation_checklist_is_covered() -> None:
    store = read("ava/agent/workflow_store.py")
    routes = read("ava/console/routes/workflow_routes.py")
    bg_tasks = read("ava/agent/bg_tasks.py")
    workflow_store = read("console-ui/src/stores/useWorkflowStore.ts")
    store_tests = read("tests/agent/test_workflow_store.py")
    route_tests = read("tests/console/test_workflow_routes.py")
    bg_task_tests = read("tests/agent/test_bg_tasks.py")

    assert_contains_all(
        store,
        [
            "class WorkflowStore",
            "TaskNodeStatus = Literal[",
            "advance_linear_chain",
            "cancel_chain",
            "retry_chain",
            "class ArtifactStore",
            "ArtifactType = Literal",
        ],
    )
    assert_contains_all(
        routes,
        [
            '@router.get("/workflows")',
            '@router.get("/artifacts")',
            '@router.websocket("/workflows/ws")',
            "workflow_events",
            "chain_event",
            "artifact_event",
            "auth.require_role(*auth.EDIT_ROLES)",
        ],
    )
    assert_contains_all(
        workflow_store,
        [
            "new WebSocket(wsUrl(workflowRealtimeQuery(filters)))",
            "JSON.parse(event.data)",
            "payload.type === 'workflow_events'",
            "set({",
            "chains: payload.chains || []",
            "artifacts: payload.artifacts || []",
        ],
    )
    assert_contains_all(bg_tasks, ["chain_id", "parent_task_ids", "streaming", "skipped"])
    assert_contains_all(
        store_tests,
        [
            "test_workflow_store_registers_chain_and_advances_linear_nodes",
            "test_workflow_store_marks_downstream_skipped_after_failed_parent",
            "test_artifact_store_indexes_task_chain_and_trace",
            "test_artifact_store_supports_p1b_artifact_types",
            "test_workflow_store_supports_streaming_terminal_paths",
            "test_workflow_store_retry_chain_preserves_trace_and_creates_new_chain",
        ],
    )
    assert_contains_all(
        route_tests,
        [
            "test_workflow_routes_list_chain_detail_and_artifacts",
            "test_workflow_node_route_advances_linear_chain",
            "test_workflow_routes_cancel_and_retry_chain",
            "test_workflow_websocket_pushes_chain_and_artifact_events",
        ],
    )
    assert_contains_all(bg_task_tests, ["chain_id=\"chain-codex\"", "parent_task_ids=[\"root-task\"]"])


def test_ava23_chain_bubble_and_status_visual_checklist_is_covered() -> None:
    types = read("console-ui/src/pages/ChatPage/types.ts")
    message_area = read("console-ui/src/pages/ChatPage/MessageArea.tsx")
    chain_bubble = read("console-ui/src/pages/ChatPage/ChainBubble.tsx")
    task_card = read("console-ui/src/pages/ChatPage/ConversationTaskCard.tsx")
    redirect_tests = read("tests/console_ui/test_redirect_matrix.py")

    for status in ["pending", "awaiting_deps", "queued", "running", "streaming", "succeeded", "failed", "cancelled", "skipped"]:
        assert status in types
        assert status in task_card
    assert_contains_all(
        message_area,
        [
            "new Map<string, DirectTaskMessage[]>",
            "taskItemsByTurn",
            "<ChainBubble",
            "suppressedTaskIds",
        ],
    )
    assert_contains_all(chain_bubble, ["data-chain-id={chainId}", "chainStatus", "ConversationTaskCard"])
    assert_contains_all(task_card, ["data-bg-task-id={task.task_id}", "查看完整日志", "TASK_STATUS_CONFIG"])
    assert "test_chat_chain_bubble_groups_direct_tasks_by_chain_id" in redirect_tests


def test_ava24_multi_agent_chat_checklist_is_covered() -> None:
    db = read("ava/storage/database.py")
    models = read("ava/console/models.py")
    service = read("ava/console/services/chat_service.py")
    routes = read("ava/console/routes/chat_routes.py")
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    input_page = read("console-ui/src/pages/ChatPage/ChatInput.tsx")
    bubble = read("console-ui/src/pages/ChatPage/MessageBubble.tsx")
    types = read("console-ui/src/pages/ChatPage/types.ts")
    chat_tests = read("tests/console/test_chat_service.py")
    route_tests = read("tests/console/test_chat_routes.py")

    assert_contains_all(db, ["from_agent_id TEXT DEFAULT ''", "mentioned_agent_ids TEXT DEFAULT '[]'"])
    assert_contains_all(models, ["participants", "ChatSessionUpdateRequest"])
    assert_contains_all(
        service,
        [
            "_parse_agent_mentions",
            "_merge_session_participants",
            "default_responder_agent_id",
            "record_console_message",
            "mentioned_agent_ids",
        ],
    )
    assert_contains_all(
        routes,
        [
            "_extract_direct_task_mention",
            "default_responder = svc_chat.get_session_default_responder_agent_id(session_id)",
            "DirectTaskService",
            "from_agent_id=task_type",
            'await _dispatch_listener_event("", event_type="complete")',
        ],
    )
    assert_contains_all(
        chat_page,
        [
            "AGENT_MENTION_RE",
            "extractAgentMentions",
            "handleParticipantsChange",
            "default_responder_agent_id",
        ],
    )
    assert_contains_all(input_page, ["AGENT_MENTIONS", "agentSuggestions", "insertAgentMention"])
    assert_contains_all(types, ["from_agent_id?: string", "mentioned_agent_ids?: string[]"])
    assert_contains_all(bubble, ["AGENT_DISPLAY", "message.from_agent_id", "message.metadata?.from_agent_id", "查看状态", "@Ta"])
    assert_contains_all(
        chat_tests,
        [
            "test_create_session_persists_participants_from_request",
            "test_record_console_message_persists_agent_metadata",
            "test_send_message_sets_agent_context_and_merges_mentions",
        ],
    )
    assert_contains_all(route_tests, ["test_extract_direct_task_mention_builds_task_prompt", "test_update_session_participants"])


def test_ava27_natural_language_skill_matching_checklist_is_covered() -> None:
    matcher = read("ava/agents/nanobot/skill_matcher.py")
    service = read("ava/console/services/chat_service.py")
    routes = read("ava/console/routes/chat_routes.py")
    chain_bubble = read("console-ui/src/pages/ChatPage/ChainBubble.tsx")
    tests = read("tests/console_ui/test_linear_acceptance_checklists.py") + read("tests/agents/test_skill_matcher.py")

    assert_contains_all(
        matcher + service + routes,
        [
            "natural_language_skill_matching",
            "match_skill_for_message",
            "skill_match_confidence",
            "我会用 skill",
            "register_skill_chain",
        ],
    )
    assert_contains_all(chain_bubble, ["skill_name", "matched_by: 'natural_language'"])
    assert "test_ava27_natural_language_skill_matching_checklist_is_covered" in tests


def test_ava38_context_size_and_compression_checklist_is_covered() -> None:
    routes = read("ava/console/routes/chat_routes.py")
    service = read("ava/console/services/chat_service.py")
    chat_header = read("console-ui/src/pages/ChatPage/ChatHeader.tsx")
    agents_dropdown = read("console-ui/src/pages/ChatPage/AgentsDropdown.tsx")
    context_chip = read("console-ui/src/pages/ChatPage/ContextChip.tsx")
    preview_service = read("ava/console/services/context_preview_service.py")
    tests = (
        read("tests/console_ui/test_linear_acceptance_checklists.py")
        + read("tests/console/test_chat_service.py")
        + read("tests/console/test_chat_routes.py")
    )

    assert_contains_all(
        routes + service,
        [
            "/sessions/{session_id}/context-size",
            "/sessions/{session_id}/compress",
            "used_tokens",
            "model_limit",
            "compression_preview",
            "before_after_diff",
            "Deprecation",
        ],
    )
    assert_contains_all(chat_header, ["<AgentsDropdown", "<ContextChip", "<ContextLensDrawer", "onParticipantsChange"])
    assert_contains_all(agents_dropdown, ["CHAT_AGENTS", "onParticipantsChange", "至少保留 1 个"])
    assert_contains_all(context_chip, ["/context-preview", "utilization_pct", "estimate_scope"])
    assert_contains_all(preview_service, ["estimate_scope", "replay_window_pre_trim", '"window"'])
    import pathlib
    assert not pathlib.Path("console-ui/src/pages/ChatPage/ConversationConfigBar.tsx").exists()
    assert "test_ava38_context_size_and_compression_checklist_is_covered" in tests


def test_ava37_task_overlay_deep_link_checklist_is_covered() -> None:
    chat_page = read("console-ui/src/pages/ChatPage/index.tsx")
    overlay = read("console-ui/src/pages/ChatPage/TaskOverlay.tsx")
    redirects = read("console-ui/src/router/redirect-matrix.ts")
    bg_tasks_page = read("console-ui/src/pages/BgTasksPage.tsx")
    redirect_tests = read("tests/console_ui/test_redirect_matrix.py")

    assert_contains_all(
        chat_page,
        [
            "const view = searchParams.get('view') || null",
            "const deepLinkTaskId = searchParams.get('task_id') || null",
            "const deepLinkChainId = searchParams.get('chain_id') || null",
            "const deepLinkTraceId = searchParams.get('trace_id') || null",
            "const showTaskOverlay = view === 'tasks'",
            "next.delete('view')",
            "next.delete('task_id')",
            "next.delete('chain_id')",
            "next.delete('trace_id')",
            "<TaskOverlay",
        ],
    )
    assert_contains_all(
        overlay,
        [
            "absolute inset-0",
            "current",
            "history",
            "scheduled",
            "artifacts",
            "navigate({ pathname: '/', search: `?${next.toString()}` })",
            "<BgTasksPage embedded taskView={section} traceId={traceId} chainId={chainId} />",
        ],
    )
    assert_contains_all(
        redirects,
        [
            "{ from: '/tasks', to: '/', defaults: { view: 'tasks', task_view: 'scheduled' } }",
            "{ from: '/bg-tasks', to: '/', defaults: { view: 'tasks', task_view: 'history' } }",
            "{ from: '/media', to: '/', defaults: { view: 'tasks', task_view: 'artifacts' } }",
        ],
    )
    assert_contains_all(bg_tasks_page, ["traceId?: string | null", "chainId?: string | null", "params.set('trace_id', deepLinkTraceId)", "params.set('chain_id', deepLinkChainId)"])
    assert "test_chat_task_overlay_contract_is_trace_aware" in redirect_tests


def test_ava18_full_process_lifecycle_checklist_is_covered() -> None:
    app = read("ava/console/app.py")
    registry = read("ava/console/services/agent_registry_service.py")
    routes = read("ava/console/routes/agent_routes.py")
    manager = read("ava/agents/process_manager.py")
    agent_dashboard = read("console-ui/src/pages/AgentDashboardPage.tsx")
    registry_tests = read("tests/console/test_agent_registry_service.py")
    route_tests = read("tests/console/test_agent_routes.py")

    assert_contains_all(
        app,
        [
            "agent_process_manager: AgentProcessManager | None = None",
            "agent_lifecycle_events: list[dict[str, Any]] = field(default_factory=list)",
            "AgentProcessManager(on_event=agent_lifecycle_events.append)",
        ],
    )
    assert_contains_all(
        registry,
        [
            "process_manager: AgentProcessManager | None = None",
            "lifecycle_events: list[dict[str, Any]] | None = None",
            "def start_agent(",
            "def stop_agent(",
            "def restart_agent(",
            "def healthcheck_agent(",
            "self._apply_lifecycle_snapshot(snapshot, adapter, managed_handles)",
            '"event": event.get("event") or ""',
            'detail = f"returncode={returncode}"',
        ],
    )
    assert_contains_all(
        routes,
        [
            '"/agents/{agent_name}/process/start"',
            '"/agents/{agent_name}/process/stop"',
            '"/agents/{agent_name}/process/restart"',
            '"/agents/{agent_name}/process/health"',
            "auth.require_role(*auth.EDIT_ROLES)",
            "auth.require_role(*auth.READ_ROLES)",
        ],
    )
    assert_contains_all(
        manager,
        [
            "atexit.register(self.stop_all)",
            "start_new_session=True",
            "os.killpg(process.pid, signal.SIGKILL)",
            '"event": "exited"',
            'payload.setdefault("timestamp", time.time())',
        ],
    )
    assert_contains_all(
        agent_dashboard,
        [
            "recent_events: AgentEvent[]",
            "Recent Events",
            "agent.recent_events.map((event)",
            "{event.detail &&",
        ],
    )
    assert "test_agent_registry_process_lifecycle_start_stop_and_events" in registry_tests
    assert "test_agent_registry_surfaces_exited_process_for_frontend" in registry_tests
    assert "test_agent_process_lifecycle_routes_require_editor_and_proxy_service" in route_tests


def test_ava22_realtime_workflow_events_checklist_is_covered() -> None:
    workflow_routes = read("ava/console/routes/workflow_routes.py")
    workflow_store = read("console-ui/src/stores/useWorkflowStore.ts")
    route_tests = read("tests/console/test_workflow_routes.py")

    assert "@router.websocket" in workflow_routes
    assert "workflow_events" in workflow_routes
    assert "chain_event" in workflow_routes
    assert "artifact_event" in workflow_routes
    assert "new WebSocket" in workflow_store
    assert "payload.type === 'workflow_events'" in workflow_store
    assert "test_workflow_websocket_pushes_chain_and_artifact_events" in route_tests


def test_ava23_full_chain_bubble_ux_checklist_is_covered() -> None:
    chain_bubble = read("console-ui/src/pages/ChatPage/ChainBubble.tsx")
    task_card = read("console-ui/src/pages/ChatPage/ConversationTaskCard.tsx")
    workflow_routes = read("ava/console/routes/workflow_routes.py")
    store_tests = read("tests/agent/test_workflow_store.py")

    assert_contains_all(
        chain_bubble + task_card,
        [
            "function taskProgress",
            "progress_percent",
            "artifact_preview",
            "实时产物预览",
            "virtualizedTaskWindow",
            "max-h-[520px] overflow-y-auto",
            "/cancel",
            "/retry",
            "Retry Chain",
            "Cancel Chain",
        ],
    )
    assert '@router.post("/workflows/{chain_id}/retry")' in workflow_routes
    assert "test_workflow_store_retry_chain_preserves_trace_and_creates_new_chain" in store_tests
