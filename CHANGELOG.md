# CHANGELOG

## LiveKit 语音链路

- feat(livekit): 支持用 DashScope 替代 OpenAI 执行 STT/LLM（2026-06-28）
  - 新增 `VOICE_AGENT_AI_PROVIDER=dashscope` 配置，使用 DashScope Qwen-ASR 识别浏览器麦克风音频。
  - DashScope LLM 通过 OpenAI 兼容接口接入，补充本地和部署环境变量示例。

- fix(livekit): 修复 worker 接到房间任务后无法创建 job 进程的问题（2026-06-28）
  - 将 LiveKit job entrypoint 提升为模块级函数，避免 macOS spawn 模式下局部函数无法 pickle。
  - 通过 `JobProcess.userdata` 在子进程内初始化 settings 和 orchestrator，并补充 pickle 回归测试。

- feat(dev): 新增本地一键启动命令（2026-06-28）
  - 新增 `voice-agent-dev` console script，通过 Python 同时启动 FastAPI reload 服务和 LiveKit worker。
  - README 补充快速启动命令及其对应的两个底层进程。

- refactor(livekit): 删除未接入主链路的旧入口和预留接口（2026-06-28）
  - 移除电话 Webhook 自测路由、重复的 `/browser-call/turn` 文本接口、未使用的 LLM JSON port 和抽取 schema。
  - 精简配置、部署模板、README 和依赖，只保留 LiveKit 浏览器语音链路与 `/demo/turn` 文本演示。

- feat(livekit): 将浏览器语音链路迁移到 LiveKit Agent pipeline（2026-06-28）
  - 新增 LiveKit token/session 创建接口和 `voice_agent.livekit_worker`，浏览器通过 LiveKit JS SDK 加入房间。
  - worker 负责 VAD/STT/turn detection/TTS，门岗回复仍由 `CallSessionOrchestrator` 生成并通过 `session.say()` 播放。
  - 补充 LiveKit/OpenAI/ElevenLabs 环境变量、双进程启动说明、腾讯云 worker systemd 模板和对应单元测试。

- refactor(realtime-voice): 删除旧 Qwen realtime 运行时代码（2026-06-28）
  - 移除 Qwen adapter、RealtimeVoice port、DashScope 配置和显式 `websockets` 依赖。
  - 浏览器语音链路只保留 LiveKit pipeline，业务状态机不变。

## 课程笔记

- docs(course-notes): 新增生产级 AI 语音助手课程笔记（2026-06-27）
  - 基于 B 站课程链接和 DeepLearning.AI 官方课时 captions 整理语音 Agent 架构、组件取舍与延迟优化要点。
  - 补充课程代码演示、metrics 采集指标、模型替换实验，以及对停车场门岗语音代理项目的落地启发。

## Qwen-Omni-Realtime 端到端语音

- feat(realtime-voice): 实现 Qwen-Omni-Realtime 适配器，打通浏览器端到端语音对话链路（2026-06-25）
  - 基于 DashScope WebSocket (`wss://dashscope.aliyuncs.com/api-ws/v1/realtime`) 实现 `QwenRealtimeSession`，
    支持 `qwen3.5-omni-plus-realtime` 模型的 `text+audio` 双模态实时通信。
  - 扩展 `RealtimeVoiceSession` 协议，新增 `commit_audio`、`receive_event`、`clear_audio` 方法及 `RealtimeVoiceEvent` 数据类型。
  - `browser_audio_stream` WebSocket handler 重写为双 task 并发架构：`receive_from_browser` 负责接收浏览器
    PCM 音频并 relay 到 Qwen，`forward_qwen_events` 负责将 Qwen 返回的音频和转写事件下发浏览器。
  - 浏览器端删除 `SpeechRecognition` / `SpeechSynthesis` 依赖，改为纯音频桥：
    麦克风 → AudioWorklet → base64 PCM → WebSocket → Qwen → 二进制音频 → AudioContext 播放。
    新增基于 RMS 能量的 VAD 静音检测（800ms 阈值）自动切分 turn。
  - 后台监听 `input_audio_transcription.completed` 事件，将转写文本喂入 `CallSessionOrchestrator` 更新访客登记状态。
  - `server.py` 注入 `QwenRealtimeProvider`，gatekeeper system prompt 作为 Qwen 系统指令。
  - 修复事件名：音频输出为 `response.audio.delta`（非 `response.output_audio.delta`），
    文本转写为 `response.audio_transcript.delta`。
  - 默认模型修正为 `qwen3.5-omni-plus-realtime`（`qwen-omni-turbo-realtime` 在此 key 下无权限）。

## 企业微信通知

- feat(wecom): 通话结束时通过企业微信 Webhook 发送访客摘要（2026-06-25）
  - `WeComGroupBotNotifier` 新增 `send_session_summary`，格式化包含字段完整度和完整对话记录的 markdown 消息。
  - `CallSessionOrchestrator` 新增 `notify_session_end`，标记会话 `ended` 并触发摘要通知。
  - `browser_audio_stream` cleanup 段调用 `notify_session_end`，确保每次通话结束都有通知。
  - `Notifier` 协议扩展 `send_session_summary` 方法。

- chore: 依赖与配置变更（2026-06-25）
  - `pyproject.toml` 新增 `websockets>=14.0` 依赖。
  - 防御性处理：`server.py` 在 `DASHSCOPE_API_KEY` 未配置时不创建 provider。
  - `gatekeeper_system_prompt.py` 补充中文问候语指令。

## 浏览器电话接入

- feat(browser-call): 新增浏览器模拟电话接入页面和音频预埋通道（2026-06-25）
  - 提供 `/browser-call` 页面、会话创建和文本转写接口，复用现有访客登记编排逻辑。
  - 新增 `/browser-call/audio` WebSocket，用于接收 16kHz PCM 音频帧并记录统计。
  - 补充浏览器端首屏与 favicon 处理，避免本地验证时出现无关 404。
  - 修复初始问候播报后语音识别未恢复监听的问题，并对可恢复识别错误自动重试。

## 腾讯云部署

- docs(deploy): 补充腾讯云 CVM 部署文档和服务模板（2026-06-25）
  - 新增 `systemd`、Nginx 和生产环境变量模板，覆盖 FastAPI 服务托管、反向代理和 HTTPS 验证流程。
  - 在 README 中增加腾讯云部署入口，便于后续发布复用。

## 项目初始化

- feat(project): 初始化停车场门岗语音代理后端项目（2026-06-25）
  - 搭建 FastAPI 应用骨架，包含健康检查、文本演示和初始电话 Webhook 入口。
  - 建立 `app/`、`domain/`、`ports/`、`adapters/`、`routes/`、`prompts/` 分层结构。
  - 补充访客登记业务流、供应商无关接口、基础配置和单元测试入口。
