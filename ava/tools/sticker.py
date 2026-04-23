"""Sticker tool for sending Telegram stickers."""

import json
from pathlib import Path
from typing import Any

import httpx

from nanobot.agent.tools.base import Tool
from nanobot.config.loader import load_config
from ava.runtime import paths as runtime_paths

DEFAULT_STICKER_PACK_NAME = "ava_01"


def _get_sticker_config_path() -> Path:
    return runtime_paths.get_sticker_config_path()

class StickerTool(Tool):
    """Tool to send Telegram stickers."""

    def __init__(self):
        self._config = None
        self._default_chat_id = None
        self._sticker_cache: dict[str, str] | None = None
        self._sent_in_turn: bool = False
        self._sticker_config: dict | None = None

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current chat context."""
        self._default_chat_id = chat_id

    @property
    def name(self) -> str:
        return "send_sticker"

    @property
    def description(self) -> str:
        sticker_data = self._get_sticker_data()
        if not sticker_data:
            return "Send a Telegram sticker. Config not found."

        min_id = min(sticker_data.keys())
        max_id = max(sticker_data.keys())
        return (
            f"Send a Telegram sticker (ID {min_id}-{max_id}). "
            f"ONLY works on Telegram — do NOT call this tool on other channels "
            f"(console, feishu, discord, etc.). "
            f"Use to express emotions visually."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        sticker_data = self._get_sticker_data()
        if sticker_data:
            min_id = min(sticker_data.keys())
            max_id = max(sticker_data.keys())
        else:
            min_id, max_id = 1, 24

        # Compact: just "1=👍, 2=😉, ..."
        parts = []
        for sid in sorted((sticker_data or {}).keys()):
            info = sticker_data[sid]
            emoji = info.get("emoji", "")
            parts.append(f"{sid}={emoji}")
        sticker_desc = ", ".join(parts) if parts else f"ID {min_id}-{max_id}"

        return {
            "type": "object",
            "properties": {
                "sticker_id": {
                    "type": "integer",
                    "description": f"Sticker ID ({min_id}-{max_id}): {sticker_desc}",
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional: Telegram chat ID.",
                },
            },
            "required": ["sticker_id"],
        }

    def _load_sticker_config(self) -> dict:
        """Load sticker pack config and cache the result."""
        if self._sticker_config is not None:
            return self._sticker_config

        config_path = _get_sticker_config_path()
        if not config_path.exists():
            self._sticker_config = {}
            return self._sticker_config

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._sticker_config = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._sticker_config = {}

        return self._sticker_config

    def _get_pack(self, pack_name: str | None = None) -> dict:
        """Get the active sticker pack config."""
        config = self._load_sticker_config()
        packs = config.get("packs", {})

        if pack_name and pack_name in packs:
            return packs[pack_name]

        if packs:
            return next(iter(packs.values()))

        return {}

    def _get_pack_name(self) -> str:
        """Get the active pack's Telegram sticker set name."""
        pack = self._get_pack()
        return pack.get("name", DEFAULT_STICKER_PACK_NAME)

    def _get_sticker_data(self) -> dict[int, dict]:
        """Get {sticker_id: {"emoji": ..., "meaning": ..., "aliases": [...]}} from config."""
        pack = self._get_pack()
        raw = pack.get("stickers", {})
        result: dict[int, dict] = {}
        for key, value in raw.items():
            try:
                sid = int(key)
                if isinstance(value, dict):
                    result[sid] = value
                else:
                    result[sid] = {"emoji": value, "meaning": "", "aliases": []}
            except (ValueError, TypeError):
                continue
        return result

    def _get_config(self) -> dict:
        """Load config and extract telegram settings."""
        if not self._config:
            config = load_config()
            tg = config.channels.telegram
            self._config = {
                "token": tg.token,
                "proxy": tg.proxy,
            }
        return self._config

    def _build_client(self, proxy: str | None) -> httpx.Client:
        """Build an httpx client with optional SOCKS5 proxy support."""
        # Ensure socks5:// is converted to socks5h:// for DNS-over-proxy
        if proxy and proxy.startswith("socks5://"):
            proxy = "socks5h://" + proxy[len("socks5://"):]
        return httpx.Client(proxy=proxy, timeout=15)

    def _get_sticker_file_ids(self, token: str, pack_name: str, proxy: str | None) -> dict[str, str]:
        """Fetch all sticker file_ids from the pack and cache them. Returns emoji->file_id map."""
        if self._sticker_cache is not None:
            return self._sticker_cache

        url = f"https://api.telegram.org/bot{token}/getStickerSet?name={pack_name}"
        try:
            with self._build_client(proxy) as client:
                response = client.get(url)
                data = response.json()

            if data.get("ok"):
                sticker_set = data.get("result", {})
                stickers = sticker_set.get("stickers", [])
                cache = {}
                for sticker in stickers:
                    emoji = sticker.get("emoji")
                    file_id = sticker.get("file_id")
                    if emoji and file_id and emoji not in cache:
                        cache[emoji] = file_id
                self._sticker_cache = cache
                return cache
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            return {}

        return {}

    def _send_sticker(self, token: str, chat_id: str, file_id: str, proxy: str | None) -> tuple[bool, str]:
        """Send sticker to chat."""
        url = f"https://api.telegram.org/bot{token}/sendSticker"
        payload = {
            "chat_id": chat_id,
            "sticker": file_id,
        }

        try:
            with self._build_client(proxy) as client:
                response = client.post(url, json=payload)
                result = response.json()

            if result.get("ok"):
                return True, "Sticker sent successfully"
            return False, result.get("description", "Unknown error")
        except httpx.HTTPError as e:
            return False, f"Network error: {e}"
        except json.JSONDecodeError as e:
            return False, f"Response parse error: {e}"

    async def execute(self, sticker_id: int, chat_id: str | None = None, **kwargs) -> str:
        """Execute the sticker send."""
        sticker_data = self._get_sticker_data()
        if not sticker_data:
            return f"Error: No sticker config found at {_get_sticker_config_path()}"

        min_id = min(sticker_data.keys())
        max_id = max(sticker_data.keys())
        if not min_id <= sticker_id <= max_id:
            return f"Error: Sticker ID must be between {min_id}-{max_id}, got {sticker_id}"

        sticker_info = sticker_data.get(sticker_id)
        if not sticker_info:
            return f"Error: No sticker mapped for sticker_id {sticker_id}"

        cfg = self._get_config()
        token = cfg.get("token")
        proxy = cfg.get("proxy")

        if not token:
            return f"Error: Telegram token not configured in {runtime_paths.get_config_path()}"

        target_chat_id = chat_id or self._default_chat_id
        if not target_chat_id:
            return "Error: No chat_id provided and no default chat context"

        emoji = sticker_info.get("emoji")
        if not emoji:
            return f"Error: No emoji defined for sticker_id {sticker_id} in config"

        pack_name = self._get_pack_name()
        file_id_map = self._get_sticker_file_ids(token, pack_name, proxy)
        file_id = file_id_map.get(emoji)
        if not file_id:
            return f"Error: Could not find sticker with emoji {emoji} in pack {pack_name}"

        success, msg = self._send_sticker(token, target_chat_id, file_id, proxy)
        if success:
            self._sent_in_turn = True
            return f"send_sticker, {emoji}"
        return f"Error: {msg}"
