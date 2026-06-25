# CHANGELOG

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
  - 搭建 FastAPI 应用骨架，包含健康检查、文本演示和 Twilio Webhook 入口。
  - 建立 `app/`、`domain/`、`ports/`、`adapters/`、`routes/`、`prompts/` 分层结构。
  - 补充访客登记业务流、供应商无关接口、基础配置和单元测试入口。
