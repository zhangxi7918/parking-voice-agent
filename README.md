# 停车场门岗语音代理

这是一个面向停车场门岗场景的 Python 后端服务，用浏览器语音完成访客信息采集、会话编排和企业微信群通知。

当前的生产链路设计如下：

```text
LiveKit 浏览器语音房间
  -> 通话会话编排器
  -> LiveKit Agent STT/VAD/TTS pipeline
  -> 访客登记状态机
  -> 访客数据仓储
  -> 企业微信群机器人通知
```

`tech-selection/` 目录保存技术选型阶段的供应商压测、冒烟测试和对比实验产物。正式应用代码放在 `src/voice_agent/` 下。

## 架构

```text
src/voice_agent/
  server.py                         FastAPI 应用工厂
  config.py                         环境变量与配置
  routes/                           HTTP 和 WebSocket 入口
  app/                              用例编排层
  domain/                           业务模型与会话状态
  ports/                            与供应商无关的接口定义
  adapters/                         企微、数据库等外部实现
  prompts/                          智能体提示词
```

核心约束：`domain/` 和 `app/` 不感知任何供应商 SDK 或协议细节。所有供应商相关实现都应放在 `adapters/` 下。

## 本地启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
voice-agent-dev
```

启动后访问健康检查：

```text
http://127.0.0.1:8000/health
```

`voice-agent-dev` 会同时启动 FastAPI 和 LiveKit Agent worker，相当于在两个终端分别运行：

```bash
uvicorn voice_agent.server:create_app --factory --reload
python -m voice_agent.livekit_worker dev
```

如果需要分别调试两个进程，也可以手动使用上面两条命令。

FastAPI 进程负责页面、文本调试接口和 LiveKit token；worker 进程负责加入 LiveKit room，
处理 VAD/STT/turn detection/TTS，并复用同一个 SQLite 会话库和企业微信通知配置。

## 腾讯云 CVM 部署

生产部署可以使用 `deploy/tencent-cloud/` 下的 `systemd` 和 Nginx 模板，完整步骤见
[`docs/deployment/tencent-cloud-cvm.md`](docs/deployment/tencent-cloud-cvm.md)。

## 文本演示

在接入浏览器语音前，可以先用文本接口验证业务流程：

```bash
curl -s http://127.0.0.1:8000/demo/turn \
  -H 'content-type: application/json' \
  -d '{"caller_text":"你好，我叫张师傅，手机号是13800138000，车牌沪A12345，来找王经理送货"}'
```

如果 `WECOM_WEBHOOK_URL` 为空，或 `NOTIFICATION_DRY_RUN=true`，系统不会真的发送企业微信群消息，只会记录通知内容，并将发送结果标记为跳过。

## 浏览器电话接入

如果你想先用浏览器模拟电话接入，可以直接打开：

```text
http://127.0.0.1:8000/browser-call
```

这个页面会向 `/browser-call/sessions` 创建本地会话并获取 LiveKit token，随后用
LiveKit JS SDK 加入房间、打开麦克风并播放 worker 返回的门岗语音。门岗回复仍由
`CallSessionOrchestrator` 和访客登记状态机生成，LiveKit 只负责实时媒体、转写、轮次检测和 TTS。

## 环境变量

```text
DATABASE_PATH             SQLite 数据库路径
WECOM_WEBHOOK_URL         企业微信群机器人 Webhook
NOTIFICATION_DRY_RUN      设为 true 时不发送外部通知
LIVEKIT_URL               LiveKit WebSocket URL，例如 wss://your-project.livekit.cloud
LIVEKIT_API_KEY           LiveKit API Key，用于签发浏览器 room token 和 worker 连接
LIVEKIT_API_SECRET        LiveKit API Secret
LIVEKIT_AGENT_NAME        LiveKit agent dispatch 名称，默认 parking-gatekeeper
VOICE_AGENT_AI_PROVIDER   STT/LLM provider，支持 openai 或 dashscope，默认 openai
OPENAI_API_KEY            provider=openai 时，LiveKit worker 中 OpenAI STT/LLM 插件使用
DASHSCOPE_API_KEY         provider=dashscope 时，DashScope Qwen-ASR/Qwen LLM 使用
DASHSCOPE_BASE_URL        DashScope OpenAI 兼容接口 base URL，默认北京地域
DASHSCOPE_ASR_MODEL       DashScope ASR 模型，默认 qwen3-asr-flash
DASHSCOPE_LLM_MODEL       DashScope LLM 模型，默认 qwen-plus
ELEVENLABS_API_KEY        LiveKit worker 中 ElevenLabs TTS 插件使用
ELEVENLABS_VOICE_ID       可选，ElevenLabs 音色 ID
```

如果 OpenAI 没有额度，可以临时切到 DashScope：

```env
VOICE_AGENT_AI_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-...
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_ASR_MODEL=qwen3-asr-flash
DASHSCOPE_LLM_MODEL=qwen-plus
```

切换后需要重启 `voice-agent-dev`，worker 子进程才会重新读取环境变量。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
