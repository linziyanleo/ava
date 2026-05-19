"""Browser data substrate (AVA-58).

Action/data-level browser primitives that sit beside `page_agent` (task-level)
and `mcp_playwright_daily_*` (precise UI). v1 surface:

* `BrowserFetchTool`        — read-only GET/HEAD against the live tab origin
* `BrowserEventsTool`       — DevTools incremental evidence (network/console/errors)
* `SiteAdapterListTool`     — local read-only adapter discovery
* `SiteAdapterInfoTool`
* `SiteAdapterRunTool`

Safety boundary lives in `fetch_tool.py` and `adapter_registry.py`.
Per-tab event caching lives in `event_cache.py`.
"""

from ava.tools.browser_substrate.client import (
    BrowserSubstrateClient,
    MCPToolMissing,
    SubstrateError,
)
from ava.tools.browser_substrate.event_cache import (
    CachedEvent,
    EventType,
    TabEventCache,
)
from ava.tools.browser_substrate.adapter_registry import (
    AdapterRejected,
    SiteAdapterManifest,
    SiteAdapterRegistry,
    SiteAdapterStep,
)
from ava.tools.browser_substrate.adapter_runner import (
    AdapterRunner,
    AdapterRunResult,
    AdapterStepFailed,
)
from ava.tools.browser_substrate.adapter_tools import (
    SiteAdapterInfoTool,
    SiteAdapterListTool,
    SiteAdapterRunTool,
)
from ava.tools.browser_substrate.events_tool import BrowserEventsTool
from ava.tools.browser_substrate.fetch_tool import BrowserFetchTool
from ava.tools.browser_substrate.registration import (
    SubstrateConfigurationError,
    register_browser_substrate_tools,
)

__all__ = [
    "AdapterRejected",
    "AdapterRunResult",
    "AdapterRunner",
    "AdapterStepFailed",
    "BrowserEventsTool",
    "BrowserFetchTool",
    "BrowserSubstrateClient",
    "CachedEvent",
    "EventType",
    "MCPToolMissing",
    "SiteAdapterInfoTool",
    "SiteAdapterListTool",
    "SiteAdapterManifest",
    "SiteAdapterRegistry",
    "SiteAdapterRunTool",
    "SiteAdapterStep",
    "SubstrateConfigurationError",
    "SubstrateError",
    "TabEventCache",
    "register_browser_substrate_tools",
]
