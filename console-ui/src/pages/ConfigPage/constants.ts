export const FIELD_INFO: Record<string, string> = {
  // agents.defaults
  'agents.defaults.workspace': '代理的工作目录路径',
  'agents.defaults.model': '主力模型，格式为 provider/model-name',
  'agents.defaults.visionModel': '视觉/OCR 任务使用的模型，留空回退到主模型',
  'agents.defaults.miniModel': '轻量任务使用的小模型，留空回退到主模型',
  'agents.defaults.voiceModel': '语音转写模型，格式 provider/model (如 groq/whisper-large-v3)，留空使用 Groq 默认',
  'agents.defaults.memoryTier': '记忆整合使用的模型层级 (default / mini)',
  'agents.defaults.provider': '指定 provider 或 auto 自动匹配',
  'agents.defaults.maxTokens': '单次 LLM 调用最大生成 token 数',
  'agents.defaults.temperature': '模型温度，越高越随机 (0-2)',
  'agents.defaults.maxToolIterations': '单轮对话中工具调用最大迭代次数',
  'agents.defaults.memoryWindow': '记忆窗口大小',
  'agents.defaults.reasoningEffort': '推理力度: low / medium / high，启用思考模式',
  // contextCompression
  'agents.defaults.contextCompression.enabled': '是否启用上下文压缩',
  'agents.defaults.contextCompression.maxChars': '压缩后历史文本最大字符数',
  'agents.defaults.contextCompression.recentTurns': '始终保留最近的对话轮数',
  'agents.defaults.contextCompression.minRecentTurns': '预算裁剪时保留的最少轮数',
  'agents.defaults.contextCompression.maxOldTurns': '按相关性保留的旧轮数上限',
  'agents.defaults.contextCompression.enableHistoryLookupHint': '压缩后缺少关键词时添加 memory.search_history 提示',
  'agents.defaults.contextCompression.protectedRecentMessages': '完全不压缩的最近消息数',
  'agents.defaults.contextCompression.bootstrapMaxChars': '引导文件(AGENTS.md等)总大小上限',
  // inLoopTruncation
  'agents.defaults.inLoopTruncation.enabled': '是否启用工具输出截断',
  'agents.defaults.inLoopTruncation.readFile': 'read_file 工具输出截断上限(字符)',
  'agents.defaults.inLoopTruncation.exec': 'exec 工具输出截断上限(字符)',
  'agents.defaults.inLoopTruncation.webFetch': 'web_fetch 工具输出截断上限(字符)',
  'agents.defaults.inLoopTruncation.default': '其他工具输出截断的默认上限(字符)',
  // token_stats
  'token_stats.enabled': '是否启用 Token 用量统计',
  'token_stats.record_full_request_payload': '记录完整的 LLM 请求负载（含消息上下文），会大幅增加存储用量',
  // channels
  channels: '消息渠道配置，每个渠道可独立启用/禁用',
  'channels.whatsapp': 'WhatsApp 消息渠道',
  'channels.telegram': 'Telegram 机器人渠道',
  'channels.discord': 'Discord 机器人渠道',
  'channels.feishu': '飞书/Lark WebSocket 长连接渠道',
  'channels.mochat': 'Mochat 聊天渠道',
  'channels.dingtalk': '钉钉 Stream 模式渠道',
  'channels.email': '邮件渠道 (IMAP 收 + SMTP 发)',
  'channels.slack': 'Slack Socket 模式渠道',
  'channels.qq': 'QQ 官方机器人渠道',
  'channels.matrix': 'Matrix (Element) 聊天渠道',
  // providers
  providers: 'LLM 服务商配置，每个服务商有 API Key 和 Base URL',
  // gateway
  'gateway.host': '网关监听地址',
  'gateway.port': '网关监听端口',
  // heartbeat (under agents.defaults)
  'agents.defaults.heartbeat.enabled': '是否启用心跳检测',
  'agents.defaults.heartbeat.interval_s': '心跳间隔(秒)',
  'agents.defaults.heartbeat.phrase1.model': 'Phase 1 (决策阶段) 使用的模型，留空使用 miniModel',
  'agents.defaults.heartbeat.phrase2.model': 'Phase 2 (执行阶段) 使用的模型，留空使用主模型',
  'gateway.console.enabled': '是否启用 Web 控制台',
  'gateway.console.port': 'Web 控制台端口',
  'gateway.console.secretKey': 'JWT 签名密钥',
  'gateway.console.tokenExpireMinutes': 'Token 过期时间(分钟)',
  // tools
  'tools.web.proxy': '网页工具 HTTP/SOCKS5 代理',
  'tools.web.search.apiKey': 'Brave Search API 密钥',
  'tools.web.search.maxResults': '搜索结果最大条数',
  'tools.exec.timeout': 'Shell 命令执行超时(秒)',
  'tools.exec.pathAppend': '追加到 PATH 的额外路径',
  'tools.exec.autoVenv': '自动检测并激活 workspace 下的 Python venv (.venv/venv)',
  'tools.restrictToWorkspace': '是否限制工具访问仅限工作目录',
  'tools.restrictConfigFile': '是否禁止代理读写 config.json (含 API Key 等敏感信息)',
  'tools.mcpServers': 'MCP 服务器连接配置',
};

const SENSITIVE_KEYS = [
  'apiKey', 'token', 'appSecret', 'clientSecret', 'secret',
  'encryptKey', 'verificationToken', 'imapPassword', 'smtpPassword',
  'botToken', 'appToken', 'clawToken', 'accessToken', 'secretKey',
]

export function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEYS.some(sk => key === sk || key.endsWith(sk.charAt(0).toUpperCase() + sk.slice(1)))
}
