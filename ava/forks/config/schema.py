"""基于上游 schema 的 sidecar 配置模型。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings

from ava.adapters.nanobot.discovery import resolve_nanobot_checkout


def _load_upstream_schema() -> ModuleType:
    """加载未打 patch 的上游 schema，供本地 fork 继承。"""
    injected = globals().get("_ava_upstream_schema")
    if isinstance(injected, ModuleType):
        injected_path = getattr(injected, "__file__", None)
        current_path = Path(__file__).resolve()
        if (
            not getattr(injected, "_ava_fork", False)
            and injected_path
            and Path(injected_path).resolve() != current_path
        ):
            return injected

    module_name = "_ava_upstream_config_schema"
    cached = sys.modules.get(module_name)
    if isinstance(cached, ModuleType):
        return cached

    upstream_path = resolve_nanobot_checkout().schema_file
    spec = importlib.util.spec_from_file_location(module_name, upstream_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载上游 schema: {upstream_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_UPSTREAM = _load_upstream_schema()

_SIDECAR_PROVIDER_NAMES = ("zenmux", "yunwu")


def _dump_field_name(field_name: str, field_info: Any, by_alias: bool) -> str:
    """按当前 dump 选项解析字段输出名。"""
    if not by_alias:
        return field_name
    return field_info.serialization_alias or field_info.alias or field_name


def _dump_model_like(
    model: BaseModel,
    *,
    mode: str,
    by_alias: bool,
    exclude_none: bool,
) -> dict[str, Any]:
    """显式递归 dump 当前模型字段，避免继承模型沿用上游 serializer。"""
    data: dict[str, Any] = {}
    for field_name, field_info in type(model).model_fields.items():
        if field_info.exclude is True:
            continue

        value = getattr(model, field_name)
        if exclude_none and value is None:
            continue

        key = _dump_field_name(field_name, field_info, by_alias)
        data[key] = _dump_value(value, mode=mode, by_alias=by_alias, exclude_none=exclude_none)

    extras = getattr(model, "__pydantic_extra__", None) or {}
    for key, value in extras.items():
        if exclude_none and value is None:
            continue
        data[key] = _dump_value(value, mode=mode, by_alias=by_alias, exclude_none=exclude_none)

    return data


def _dump_value(
    value: Any,
    *,
    mode: str,
    by_alias: bool,
    exclude_none: bool,
) -> Any:
    """递归序列化嵌套值。"""
    if isinstance(value, BaseModel):
        return _dump_model_like(value, mode=mode, by_alias=by_alias, exclude_none=exclude_none)
    if isinstance(value, Path):
        return str(value) if mode == "json" else value
    if isinstance(value, dict):
        return {
            key: _dump_value(item, mode=mode, by_alias=by_alias, exclude_none=exclude_none)
            for key, item in value.items()
            if not (exclude_none and item is None)
        }
    if isinstance(value, list):
        return [
            _dump_value(item, mode=mode, by_alias=by_alias, exclude_none=exclude_none)
            for item in value
            if not (exclude_none and item is None)
        ]
    if isinstance(value, tuple):
        dumped = [
            _dump_value(item, mode=mode, by_alias=by_alias, exclude_none=exclude_none)
            for item in value
            if not (exclude_none and item is None)
        ]
        return dumped if mode == "json" else tuple(dumped)
    return value


class Base(_UPSTREAM.Base):
    """沿用上游 alias / populate 规则的基础模型。"""


class WhatsAppConfig(Base):
    """WhatsApp 渠道配置。"""

    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class TelegramConfig(Base):
    """Telegram 渠道配置。"""

    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    proxy: str | None = None
    reply_to_message: bool = False
    react_emoji: str = "👀"
    group_policy: Literal["open", "mention"] = "mention"
    connection_pool_size: int = 32
    pool_timeout: float = 5.0
    streaming: bool = True
    stream_edit_interval: float = 0.6
    user_typing_timeout: int = 0


class FeishuConfig(Base):
    """飞书渠道配置。"""

    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    react_emoji: str = "THUMBSUP"


class DingTalkConfig(Base):
    """钉钉渠道配置。"""

    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    allow_from: list[str] = Field(default_factory=list)


class DiscordConfig(Base):
    """Discord 渠道配置。"""

    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377


class EmailConfig(Base):
    """Email 渠道配置。"""

    enabled: bool = False
    consent_granted: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""
    auto_reply_enabled: bool = True
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)


class MochatMentionConfig(Base):
    """Mochat 提及行为配置。"""

    require_in_groups: bool = False


class MochatGroupRule(Base):
    """Mochat 群级规则。"""

    require_mention: bool = False


class MochatConfig(Base):
    """Mochat 渠道配置。"""

    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = ""
    socket_path: str = "/socket.io"
    socket_disable_msgpack: bool = False
    socket_reconnect_delay_ms: int = 1000
    socket_max_reconnect_delay_ms: int = 10000
    socket_connect_timeout_ms: int = 10000
    refresh_interval_ms: int = 30000
    watch_timeout_ms: int = 25000
    watch_limit: int = 100
    retry_delay_ms: int = 500
    max_retry_attempts: int = 0
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"
    reply_delay_ms: int = 120000


class SlackDMConfig(Base):
    """Slack 私聊策略。"""

    enabled: bool = True
    policy: str = "open"
    allow_from: list[str] = Field(default_factory=list)


class SlackConfig(Base):
    """Slack 渠道配置。"""

    enabled: bool = False
    mode: str = "socket"
    webhook_path: str = "/slack/events"
    bot_token: str = ""
    app_token: str = ""
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    done_emoji: str = "white_check_mark"
    allow_from: list[str] = Field(default_factory=list)
    group_policy: str = "mention"
    group_allow_from: list[str] = Field(default_factory=list)
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)


class QQConfig(Base):
    """QQ 渠道配置。"""

    enabled: bool = False
    app_id: str = ""
    secret: str = ""
    allow_from: list[str] = Field(default_factory=list)


class MatrixConfig(Base):
    """Matrix 渠道配置。"""

    enabled: bool = False
    homeserver: str = "https://matrix.org"
    access_token: str = ""
    user_id: str = ""
    device_id: str = ""
    e2ee_enabled: bool = True
    sync_stop_grace_seconds: int = 2
    max_media_bytes: int = 20 * 1024 * 1024
    allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["open", "mention", "allowlist"] = "open"
    group_allow_from: list[str] = Field(default_factory=list)
    allow_room_mentions: bool = False


class ChannelsConfig(_UPSTREAM.ChannelsConfig):
    """在上游 extra=allow 的基础上，保留 sidecar 常用内建渠道默认结构。"""

    model_config = _UPSTREAM.ChannelsConfig.model_config

    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    matrix: MatrixConfig = Field(default_factory=MatrixConfig)


class ContextCompressionConfig(Base):
    """历史压缩配置。"""

    enabled: bool = True
    max_chars: int = 50000
    recent_turns: int = 10
    min_recent_turns: int = 4
    max_old_turns: int = 6
    protected_recent_messages: int = 20
    enable_history_lookup_hint: bool = True
    bootstrap_max_chars: int = 16000


class InLoopTruncationConfig(Base):
    """单轮内工具输出截断配置。"""

    enabled: bool = True
    read_file: int = 16000
    exec: int = 8000
    web_fetch: int = 12000
    claude_code: int = 16000
    default: int = 8000

    def limit_for(self, tool_name: str) -> int:
        """返回指定工具的截断上限。"""
        return getattr(self, tool_name, self.default)


class HistorySummarizerConfig(Base):
    """历史摘要配置。"""

    enabled: bool = True
    protect_recent: int = 6
    tool_result_max_chars: int = 400


class HeartbeatPhaseConfig(Base):
    """心跳阶段级模型覆盖配置。"""

    model: str = ""


class DreamConfig(_UPSTREAM.DreamConfig):
    """沿用上游 Dream 配置结构，供 sidecar fork 显式继承。"""


class AgentDefaults(_UPSTREAM.AgentDefaults):
    """sidecar 扩展后的默认 agent 配置。"""

    model: str = "anthropic/claude-opus-4-6"
    vision_model: str = "google/gemini-3.1-flash-lite-preview"
    mini_model: str = "google/gemini-3.1-flash-lite-preview"
    image_gen_model: str = "google/gemini-3.1-flash-image-preview"
    memory_tier: Literal["default", "mini"] | None = "default"
    memory_window: int = 100
    context_compression: ContextCompressionConfig = Field(default_factory=ContextCompressionConfig)
    in_loop_truncation: InLoopTruncationConfig = Field(default_factory=InLoopTruncationConfig)
    history_summarizer: HistorySummarizerConfig = Field(default_factory=HistorySummarizerConfig)
    dream: DreamConfig = Field(default_factory=DreamConfig)
    heartbeat: "HeartbeatConfig" = Field(default_factory=lambda: HeartbeatConfig())


class AgentsConfig(_UPSTREAM.AgentsConfig):
    """使用 sidecar AgentDefaults。"""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(_UPSTREAM.ProviderConfig):
    """沿用上游 provider 配置。"""


class ProvidersConfig(_UPSTREAM.ProvidersConfig):
    """在上游 providers 基础上补 sidecar 私有 provider。"""

    zenmux: ProviderConfig = Field(default_factory=ProviderConfig)
    yunwu: ProviderConfig = Field(default_factory=ProviderConfig)
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig, exclude=True)
    github_copilot: ProviderConfig = Field(default_factory=ProviderConfig, exclude=True)


class ConsoleConfig(Base):
    """Web Console 配置。"""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 6688
    secret_key: str = "change-me-in-production-use-a-longer-key!"
    token_expire_minutes: int = 480
    public_dev: bool = Field(
        default=False,
        validation_alias=AliasChoices("public_dev", "publicDev"),
        serialization_alias="publicDev",
    )
    session_cookie_name: str = Field(
        default="ava_console_session",
        validation_alias=AliasChoices("session_cookie_name", "sessionCookieName"),
        serialization_alias="sessionCookieName",
    )
    session_cookie_secure: bool = Field(
        default=False,
        validation_alias=AliasChoices("session_cookie_secure", "sessionCookieSecure"),
        serialization_alias="sessionCookieSecure",
    )
    session_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        validation_alias=AliasChoices("session_cookie_samesite", "sessionCookieSameSite"),
        serialization_alias="sessionCookieSameSite",
    )
    cloudflare_access_team_domain: str = Field(
        default="",
        validation_alias=AliasChoices("cloudflare_access_team_domain", "cloudflareAccessTeamDomain"),
        serialization_alias="cloudflareAccessTeamDomain",
    )
    cloudflare_access_audience: str = Field(
        default="",
        validation_alias=AliasChoices("cloudflare_access_audience", "cloudflareAccessAudience"),
        serialization_alias="cloudflareAccessAudience",
    )


class HeartbeatConfig(Base):
    """在上游心跳配置上补充分阶段模型覆盖。"""

    enabled: bool = True
    interval_s: int = Field(
        default=30 * 60,
        validation_alias=AliasChoices("interval_s", "intervalS"),
        serialization_alias="interval_s",
    )
    keep_recent_messages: int = Field(
        default=8,
        validation_alias=AliasChoices("keep_recent_messages", "keepRecentMessages"),
        serialization_alias="keep_recent_messages",
    )
    phrase1: HeartbeatPhaseConfig = Field(default_factory=HeartbeatPhaseConfig)
    phrase2: HeartbeatPhaseConfig = Field(default_factory=HeartbeatPhaseConfig)


class ApiConfig(_UPSTREAM.ApiConfig):
    """沿用上游 API 配置。"""


class GatewayConfig(Base):
    """在上游 gateway 基础上挂 sidecar console。"""

    host: str = "0.0.0.0"
    port: int = 18790
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    console: ConsoleConfig = Field(default_factory=ConsoleConfig)


class WebSearchConfig(_UPSTREAM.WebSearchConfig):
    """沿用上游 Web 搜索配置。"""


    provider: str = "brave"


class WebToolsConfig(_UPSTREAM.WebToolsConfig):
    """沿用上游 Web 工具配置。"""


    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(_UPSTREAM.ExecToolConfig):
    """为 sidecar exec 工具补充 auto_venv。"""

    auto_venv: bool = True


class MCPServerConfig(_UPSTREAM.MCPServerConfig):
    """沿用上游 MCP 配置。"""


class ClaudeCodeConfig(Base):
    """Claude Code 工具配置。"""

    default_project: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_turns: int = 15
    allowed_tools: str = "Read,Edit,Bash,Glob,Grep"
    timeout: int = 600
    api_key: str = ""
    base_url: str = ""


class PageAgentConfig(Base):
    """通用 PageAgent 页面操作工具配置。"""

    enabled: bool = True
    api_base: str = Field(
        default="",
        validation_alias=AliasChoices("api_base", "apiBase"),
        serialization_alias="apiBase",
    )
    api_key: str = Field(
        default="",
        validation_alias=AliasChoices("api_key", "apiKey"),
        serialization_alias="apiKey",
    )
    api_key_env: str = Field(
        default="PAGE_AGENT_API_KEY",
        validation_alias=AliasChoices("api_key_env", "apiKeyEnv"),
        serialization_alias="apiKeyEnv",
    )
    model: str = ""
    headless: bool = True
    browser_type: str = Field(
        default="chromium",
        validation_alias=AliasChoices("browser_type", "browserType"),
        serialization_alias="browserType",
    )
    viewport_width: int = Field(
        default=1280,
        validation_alias=AliasChoices("viewport_width", "viewportWidth"),
        serialization_alias="viewportWidth",
    )
    viewport_height: int = Field(
        default=720,
        validation_alias=AliasChoices("viewport_height", "viewportHeight"),
        serialization_alias="viewportHeight",
    )
    max_steps: int = Field(
        default=40,
        validation_alias=AliasChoices("max_steps", "maxSteps"),
        serialization_alias="maxSteps",
    )
    step_delay: float = Field(
        default=0.4,
        validation_alias=AliasChoices("step_delay", "stepDelay"),
        serialization_alias="stepDelay",
    )
    timeout: int = 120
    language: str = "zh-CN"
    user_data_dir: str = Field(
        default="",
        validation_alias=AliasChoices("user_data_dir", "userDataDir"),
        serialization_alias="userDataDir",
    )
    screenshot_dir: str = Field(
        default="",
        validation_alias=AliasChoices("screenshot_dir", "screenshotDir"),
        serialization_alias="screenshotDir",
    )


class ToolsConfig(_UPSTREAM.ToolsConfig):
    """在上游工具配置基础上补 sidecar 工具项。"""

    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    claude_code: ClaudeCodeConfig = Field(default_factory=ClaudeCodeConfig)
    page_agent: PageAgentConfig = Field(
        default_factory=PageAgentConfig,
        validation_alias=AliasChoices("page_agent", "pageAgent"),
        serialization_alias="pageAgent",
    )
    restrict_config_file: bool = Field(
        default=True,
        validation_alias=AliasChoices("restrictToConfigFile", "restrictConfigFile"),
        serialization_alias="restrictToConfigFile",
    )


class TokenStatsConfig(Base):
    """Token 统计配置。"""

    enabled: bool = True
    record_full_request_payload: bool = Field(
        default=False,
        validation_alias=AliasChoices("record_full_request_payload", "recordFullRequestPayload"),
        serialization_alias="record_full_request_payload",
    )


class Config(BaseSettings):
    """sidecar 根配置。"""

    model_config = _UPSTREAM.Config.model_config

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    token_stats: TokenStatsConfig = Field(default_factory=TokenStatsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        """返回展开后的 workspace 路径。"""
        return Path(self.agents.defaults.workspace).expanduser()

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """显式递归序列化，确保 sidecar 扩展字段不会在导出时退回上游结构。"""
        if args:
            return super().model_dump(*args, **kwargs)

        mode = kwargs.get("mode", "python")
        include = kwargs.get("include")
        exclude = kwargs.get("exclude")
        context = kwargs.get("context")
        by_alias = kwargs.get("by_alias", False)
        exclude_unset = kwargs.get("exclude_unset", False)
        exclude_defaults = kwargs.get("exclude_defaults", False)
        exclude_none = kwargs.get("exclude_none", False)
        round_trip = kwargs.get("round_trip", False)
        fallback = kwargs.get("fallback")
        serialize_as_any = kwargs.get("serialize_as_any", False)

        if (
            include is not None
            or exclude is not None
            or context is not None
            or exclude_unset
            or exclude_defaults
            or round_trip
            or fallback is not None
            or serialize_as_any
        ):
            return super().model_dump(*args, **kwargs)

        return _dump_model_like(
            self,
            mode=mode,
            by_alias=bool(by_alias),
            exclude_none=bool(exclude_none),
        )

    def _match_provider(
        self,
        model: str | None = None,
    ) -> tuple["ProviderConfig | None", str | None]:
        """兼容 sidecar 私有 provider，同时复用上游匹配逻辑。"""
        forced = self.agents.defaults.provider
        normalized_forced = forced.replace("-", "_")
        if normalized_forced in _SIDECAR_PROVIDER_NAMES:
            provider = getattr(self.providers, normalized_forced, None)
            return (provider, normalized_forced) if provider else (None, None)

        model_lower = (model or self.agents.defaults.model).lower()
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")
        if normalized_prefix in _SIDECAR_PROVIDER_NAMES:
            provider = getattr(self.providers, normalized_prefix, None)
            return (provider, normalized_prefix) if provider else (None, None)

        return _UPSTREAM.Config._match_provider(self, model)

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """返回匹配到的 provider 配置。"""
        provider, _ = self._match_provider(model)
        return provider

    def get_provider_name(self, model: str | None = None) -> str | None:
        """返回匹配到的 provider 名称。"""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """返回指定模型使用的 API key。"""
        provider = self.get_provider(model)
        return provider.api_key if provider else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """返回指定模型使用的 API base。"""
        from nanobot.providers.registry import find_by_name

        provider, name = self._match_provider(model)
        if provider and provider.api_base:
            return provider.api_base

        if name:
            spec = find_by_name(name)
            if spec and (spec.is_gateway or spec.is_local) and spec.default_api_base:
                return spec.default_api_base

        return None
