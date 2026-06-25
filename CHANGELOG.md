# CHANGELOG

## 腾讯云部署

- docs(deploy): 补充腾讯云 CVM 部署文档和服务模板（2026-06-25）
  - 新增 `systemd`、Nginx 和生产环境变量模板，覆盖 FastAPI 服务托管、反向代理和 HTTPS 验证流程。
  - 在 README 中增加腾讯云部署入口，便于后续发布复用。

## 项目初始化

- feat(project): 初始化停车场门岗语音代理后端项目（2026-06-25）
  - 搭建 FastAPI 应用骨架，包含健康检查、文本演示和 Twilio Webhook 入口。
  - 建立 `app/`、`domain/`、`ports/`、`adapters/`、`routes/`、`prompts/` 分层结构。
  - 补充访客登记业务流、供应商无关接口、基础配置和单元测试入口。
