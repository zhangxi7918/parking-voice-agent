# 停车场门岗语音代理

这是一个面向停车场门岗场景的 Python 后端服务，用语音电话完成访客信息采集、会话编排和企业微信群通知。

当前的生产链路设计如下：

```text
Twilio 电话 Webhook
  -> 通话会话编排器
  -> 实时语音适配器
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
  adapters/                         Twilio、Qwen、企微、数据库等实现
  prompts/                          智能体提示词与信息抽取 schema
```

核心约束：`domain/` 和 `app/` 不感知任何供应商 SDK 或协议细节。所有供应商相关实现都应放在 `adapters/` 下。

## 本地启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn voice_agent.server:create_app --factory --reload
```

启动后访问健康检查：

```text
http://127.0.0.1:8000/health
```

## 腾讯云 CVM 部署

生产部署可以使用 `deploy/tencent-cloud/` 下的 `systemd` 和 Nginx 模板，完整步骤见
[`docs/deployment/tencent-cloud-cvm.md`](docs/deployment/tencent-cloud-cvm.md)。

## 文本演示

在接入真实电话音频前，可以先用文本接口验证业务流程：

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

这个页面会用浏览器语音识别和播报完成对话闭环，同时把麦克风音频帧发到后端 `/browser-call/audio` 做连接和统计验证。当前版本不接任何实时语音供应商。

## Twilio 入口

将 Twilio 语音 Webhook 配置为：

```text
POST /twilio/voice
```

该接口会返回 TwiML，并把电话媒体流指向：

```text
WS /twilio/media
```

TwiML 会通过名为 `session_id` 的 Twilio `<Parameter>` 传递本地会话 ID。WebSocket
路由会从 `start.customParameters` 中读取并校验该 ID，接收 Twilio media stream 事件，
并记录收到的音频帧数和字节数，用于呼入链路自测。Qwen 实时语音桥接实现应放在
`src/voice_agent/adapters/qwen/` 下。

本地拨号自测：

```bash
uvicorn voice_agent.server:create_app --factory --reload
ngrok http 8000
```

将 `PUBLIC_BASE_URL` 设置为 ngrok 的 HTTPS 地址，然后在 Twilio Console 中把号码的
Voice webhook 配置为：

```text
POST {PUBLIC_BASE_URL}/twilio/voice
```

## 环境变量

```text
PUBLIC_BASE_URL           对外可访问的 HTTPS 基础 URL，供 Twilio 回调使用，例如 https://demo.example.com
DATABASE_PATH             SQLite 数据库路径
WECOM_WEBHOOK_URL         企业微信群机器人 Webhook
NOTIFICATION_DRY_RUN      设为 true 时不发送外部通知
TWILIO_ACCOUNT_SID        Twilio Account SID
TWILIO_AUTH_TOKEN         Twilio Auth Token
TWILIO_PHONE_NUMBER       用于呼入自测的 Twilio 号码
TWILIO_VALIDATE_SIGNATURE 设为 true 时校验 Twilio webhook 签名
DASHSCOPE_API_KEY         Qwen 实时 API Key
QWEN_REALTIME_MODEL       Qwen 实时模型名称
```

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
