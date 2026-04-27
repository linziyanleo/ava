"""Monkey patch to inject sidecar custom tools into AgentLoop."""

import os
import shutil

from loguru import logger

from nanobot.agent.loop import AgentLoop
from ava.launcher import register_patch

from ava.tools import (
    ClaudeCodeTool,
    CodexTool,
    GatewayControlTool,
    ImageGenTool,
    MemoryTool,
    PageAgentTool,
    StickerTool,
    VisionTool,
)


def apply_tools_patch() -> str:
    """Apply the custom tools patch to AgentLoop.

    This function:
    1. Saves the original _register_default_tools method
    2. Creates a wrapper that calls the original method first
    3. Then registers sidecar custom tools
    4. Replaces the method on AgentLoop class
    
    Returns:
        str: Description of what was patched
    """
    if not hasattr(AgentLoop, "_register_default_tools"):
        logger.warning("tools_patch skipped: AgentLoop._register_default_tools not found")
        return "tools_patch skipped (_register_default_tools not found)"

    if getattr(AgentLoop._register_default_tools, "_ava_tools_patched", False):
        return "tools_patch already applied (skipped)"

    original_register = AgentLoop._register_default_tools

    def patched_register_default_tools(self: AgentLoop) -> None:
        """Wrapper that registers default tools then adds sidecar custom tools."""
        original_register(self)
        
        from nanobot.config.loader import load_config
        config = load_config()

        # ClaudeCodeConfig is at tools.claude_code (fork schema)
        # Fallback gracefully if the field doesn't exist (vanilla schema)
        cc_cfg = getattr(getattr(config, "tools", None), "claude_code", None)
        cc_model = (cc_cfg.model if cc_cfg else None) or \
                   getattr(config.agents.defaults, "claude_code_model", None) or \
                   "claude-sonnet-4-20250514"
        cc_max_turns = cc_cfg.max_turns if cc_cfg else 15
        cc_allowed_tools = cc_cfg.allowed_tools if cc_cfg else "Read,Edit,Bash,Glob,Grep"
        cc_timeout = cc_cfg.timeout if cc_cfg else 600

        cwd = os.getcwd()
        cc_default_project = (cc_cfg.default_project if cc_cfg and cc_cfg.default_project else cwd)

        self.tools.register(ClaudeCodeTool(
            workspace=self.workspace,
            token_stats=getattr(self, 'token_stats', None),
            default_project=cc_default_project,
            model=cc_model,
            max_turns=cc_max_turns,
            allowed_tools=cc_allowed_tools,
            timeout=cc_timeout,
            subagent_manager=self.subagents,
            task_store=getattr(self, 'bg_tasks', None),
            cc_config=cc_cfg,
        ))

        # Codex tool: conditional on providers.openai_codex having an api_key,
        # or codex CLI being available (uses its own auth).
        codex_cfg = getattr(config.providers, "openai_codex", None)
        codex_api_key = (codex_cfg.api_key if codex_cfg else "") or ""
        if codex_api_key or shutil.which("codex"):
            self.tools.register(CodexTool(
                workspace=self.workspace,
                token_stats=getattr(self, 'token_stats', None),
                default_project=cwd,
                model=getattr(codex_cfg, "model", "") if codex_cfg else "",
                timeout=600,
                task_store=getattr(self, 'bg_tasks', None),
                codex_config=codex_cfg,
            ))

        image_cfg = getattr(getattr(config, "tools", None), "image_gen", None)
        self.tools.register(ImageGenTool(
            token_stats=getattr(self, 'token_stats', None),
            media_service=getattr(self, 'media_service', None),
            task_store=getattr(self, 'bg_tasks', None),
            timeout=getattr(image_cfg, "timeout", 300) if image_cfg else 300,
            background=getattr(image_cfg, "background", True) if image_cfg else True,
            auto_continue=getattr(image_cfg, "auto_continue", False) if image_cfg else False,
            auto_send=getattr(image_cfg, "auto_send", True) if image_cfg else True,
        ))

        # Vision tool: prefer vision_model if configured
        vision_model = getattr(config.agents.defaults, "vision_model", None) or self.model
        self.tools.register(VisionTool(
            provider=self.provider,
            model=vision_model,
            token_stats=getattr(self, 'token_stats', None),
        ))
        
        self.tools.register(StickerTool())

        # PageAgent tool
        pa_cfg = getattr(getattr(config, "tools", None), "page_agent", None)
        pa_enabled = pa_cfg.enabled if pa_cfg else True
        if pa_enabled:
            pa_tool = PageAgentTool(
                config=pa_cfg,
                media_service=getattr(self, 'media_service', None),
                token_stats=getattr(self, 'token_stats', None),
            )
            self.tools.register(pa_tool)

        self.tools.register(GatewayControlTool(
            lifecycle=getattr(self, 'lifecycle_manager', None),
        ))

        categorized_memory = getattr(self, 'categorized_memory', None)
        db = getattr(self, 'db', None)
        if categorized_memory:
            self.tools.register(MemoryTool(
                store=categorized_memory,
                db=db,
            ))

    patched_register_default_tools._ava_tools_patched = True
    AgentLoop._register_default_tools = patched_register_default_tools
    
    return "Registered custom tools: claude_code, codex (conditional), image_gen, vision, send_sticker, page_agent, gateway_control, memory"


register_patch('custom_tools', apply_tools_patch)
