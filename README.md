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

## 文本演示

在接入真实电话音频前，可以先用文本接口验证业务流程：

```bash
curl -s http://127.0.0.1:8000/demo/turn \
  -H 'content-type: application/json' \
  -d '{"caller_text":"你好，我叫张师傅，手机号是13800138000，车牌沪A12345，来找王经理送货"}'
```

如果 `WECOM_WEBHOOK_URL` 为空，或 `NOTIFICATION_DRY_RUN=true`，系统不会真的发送企业微信群消息，只会记录通知内容，并将发送结果标记为跳过。

## Twilio 入口

将 Twilio 语音 Webhook 配置为：

```text
POST /twilio/voice
```

该接口会返回 TwiML，并把电话媒体流指向：

```text
WS /twilio/media?session_id=<session_id>
```

当前 WebSocket 路由已经可以接收 Twilio media stream 事件，并维护完整的会话生命周期。Qwen 实时语音桥接实现应放在 `src/voice_agent/adapters/qwen/` 下。

## 环境变量

```text
PUBLIC_BASE_URL           对外可访问的 HTTPS 基础 URL，供 Twilio 回调使用，例如 https://demo.example.com
DATABASE_PATH             SQLite 数据库路径
WECOM_WEBHOOK_URL         企业微信群机器人 Webhook
NOTIFICATION_DRY_RUN      设为 true 时不发送外部通知
DASHSCOPE_API_KEY         Qwen 实时 API Key
QWEN_REALTIME_MODEL       Qwen 实时模型名称
```

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
