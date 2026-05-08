from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "console-ui/src/router/redirect-matrix.ts"
APP = ROOT / "console-ui/src/App.tsx"


def test_legacy_redirect_matrix_covers_retired_routes() -> None:
    source = MATRIX.read_text()
    paths = set(re.findall(r"from: '([^']+)'", source))

    assert {
        "/agents",
        "/config",
        "/memory",
        "/persona",
        "/skills",
        "/media",
        "/chat",
        "/tasks",
        "/bg-tasks",
        "/tokens",
        "/users",
        "/browser",
        "/gateway",
    }.issubset(paths)


def test_app_routes_use_single_redirect_matrix() -> None:
    source = APP.read_text()

    assert "legacyRedirectMatrix.map" in source
    assert "resolveLegacyRedirect" in source


def test_task_overlay_redirects_use_parameterized_chat_route() -> None:
    source = MATRIX.read_text()

    assert "{ from: '/tasks', to: '/', defaults: { view: 'tasks', task_view: 'scheduled' } }" in source
    assert "{ from: '/bg-tasks', to: '/', defaults: { view: 'tasks', task_view: 'history' } }" in source
    assert "{ from: '/media', to: '/', defaults: { view: 'tasks', task_view: 'artifacts' } }" in source


def test_chat_task_overlay_contract_is_trace_aware() -> None:
    chat_source = (ROOT / "console-ui/src/pages/ChatPage/index.tsx").read_text()
    overlay_source = (ROOT / "console-ui/src/pages/ChatPage/TaskOverlay.tsx").read_text()
    bg_tasks_source = (ROOT / "console-ui/src/pages/BgTasksPage.tsx").read_text()

    assert "view === 'tasks'" in chat_source
    assert "!!deepLinkTraceId" in chat_source
    assert "next.delete('trace_id')" in chat_source
    assert "window.addEventListener('keydown', onKeyDown)" in overlay_source
    assert "traceId={traceId}" in overlay_source
    assert "params.set('trace_id', deepLinkTraceId)" in bg_tasks_source


def test_chat_chain_bubble_groups_direct_tasks_by_chain_id() -> None:
    types_source = (ROOT / "console-ui/src/pages/ChatPage/types.ts").read_text()
    message_area_source = (ROOT / "console-ui/src/pages/ChatPage/MessageArea.tsx").read_text()
    chain_bubble_source = (ROOT / "console-ui/src/pages/ChatPage/ChainBubble.tsx").read_text()
    task_card_source = (ROOT / "console-ui/src/pages/ChatPage/ConversationTaskCard.tsx").read_text()

    assert "chain_id?: string" in types_source
    assert "parent_task_ids?: string[]" in types_source
    assert "origin_turn_seq?: number | null" in types_source
    assert "new Map<string, DirectTaskMessage[]>" in message_area_source
    assert "taskItemsByTurn" in message_area_source
    assert "<ChainBubble" in message_area_source
    assert "data-chain-id={chainId}" in chain_bubble_source
    assert "data-bg-task-id={task.task_id}" in task_card_source
    assert "查看完整日志" in task_card_source


def test_agent_detail_tabs_are_nested_under_settings_agents_config() -> None:
    app_source = APP.read_text()
    settings_source = (ROOT / "console-ui/src/pages/SettingsPage.tsx").read_text()
    agent_source = (ROOT / "console-ui/src/pages/AgentDashboardPage.tsx").read_text()
    config_source = (ROOT / "console-ui/src/pages/ConfigPage/index.tsx").read_text()

    assert 'path="agents-config/:agentKind"' in app_source
    assert 'path="agents-config/codex/config"' in app_source
    assert 'mode="codex"' in app_source
    assert 'mode="claude_code"' in app_source
    assert 'mode="image_gen"' in app_source
    assert "/settings/agents-config/codex" in settings_source
    assert "/settings/agents-config/claude-code" in settings_source
    assert "/settings/agents-config/image-gen" in settings_source
    assert "/settings/agents-config/codex/config" in settings_source
    assert "/settings/agents-config/claude-code/config" in settings_source
    assert "ROUTE_AGENT_NAME" in agent_source
    assert "function AgentDetail" in agent_source
    assert "Edit Config" in agent_source
    assert "codex-config.toml" in config_source
    assert "claude-code-settings.json" in config_source
    assert "rawContent" in config_source
