# 腾讯云 CVM 部署 FastAPI 服务

本文档用于把当前 FastAPI 服务部署到腾讯云 CVM。默认服务器系统为 Ubuntu/Debian，
应用目录为 `/opt/parking-voice-agent`，服务用户为 `voice-agent`。

## 成功标准

1. `systemd` 能托管 FastAPI 服务并自动重启。
2. Nginx 能把公网 HTTP/HTTPS 请求反代到本机 `127.0.0.1:8000`。
3. `/health` 返回正常结果。
4. `/browser-call` 页面可以创建 LiveKit 会话，LiveKit worker 可以加入房间。

## 服务器准备

在腾讯云控制台确认安全组已开放：

- `22/tcp`：SSH 登录。
- `80/tcp`：申请证书和 HTTP 访问。
- `443/tcp`：生产 HTTPS 访问。

建议准备一个域名，例如 `voice-agent.example.com`，并把 DNS 解析到 CVM 公网 IP。
没有域名时可以先用公网 IP 验证 `/health`。

## 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv nginx
```

如果需要自动申请 HTTPS 证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
```

## 创建服务用户和目录

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin voice-agent
sudo mkdir -p /opt/parking-voice-agent /etc/parking-voice-agent /var/lib/parking-voice-agent
sudo chown -R voice-agent:voice-agent /opt/parking-voice-agent /var/lib/parking-voice-agent
```

## 上传代码

在本机项目根目录执行，替换 `ubuntu@SERVER_IP`：

```bash
rsync -az --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude '.data' \
  --exclude 'tech-selection' \
  --exclude '*.m4a' \
  ./ ubuntu@SERVER_IP:/tmp/parking-voice-agent/
```

然后在服务器上安装到 `/opt`：

```bash
sudo rsync -az --delete /tmp/parking-voice-agent/ /opt/parking-voice-agent/
sudo chown -R voice-agent:voice-agent /opt/parking-voice-agent
```

## 安装 Python 依赖

```bash
sudo -u voice-agent python3 -m venv /opt/parking-voice-agent/.venv
sudo -u voice-agent /opt/parking-voice-agent/.venv/bin/pip install --upgrade pip
sudo -u voice-agent /opt/parking-voice-agent/.venv/bin/pip install -e /opt/parking-voice-agent
```

## 配置环境变量

```bash
sudo cp /opt/parking-voice-agent/deploy/tencent-cloud/voice-agent.env.example /etc/parking-voice-agent/voice-agent.env
sudo nano /etc/parking-voice-agent/voice-agent.env
sudo chmod 600 /etc/parking-voice-agent/voice-agent.env
```

至少需要确认：

- `DATABASE_PATH`：建议保留 `/var/lib/parking-voice-agent/voice-agent.sqlite3`。
- `WECOM_WEBHOOK_URL`：企业微信群机器人地址；未配置时保持 `NOTIFICATION_DRY_RUN=true`。
- `LIVEKIT_*`：浏览器语音链路需要填写 LiveKit URL、API Key、API Secret 和 agent name。
- `VOICE_AGENT_AI_PROVIDER`：STT/LLM provider，支持 `openai` 或 `dashscope`。
- `OPENAI_API_KEY`：`VOICE_AGENT_AI_PROVIDER=openai` 时使用。
- `DASHSCOPE_API_KEY`：`VOICE_AGENT_AI_PROVIDER=dashscope` 时使用，默认 ASR 为 `qwen3-asr-flash`，LLM 为 `qwen-plus`。
- `ELEVENLABS_API_KEY`：LiveKit worker 的 TTS pipeline 使用。

## 安装 systemd 服务

```bash
sudo cp /opt/parking-voice-agent/deploy/tencent-cloud/parking-voice-agent.service /etc/systemd/system/parking-voice-agent.service
sudo cp /opt/parking-voice-agent/deploy/tencent-cloud/parking-voice-agent-livekit-worker.service /etc/systemd/system/parking-voice-agent-livekit-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now parking-voice-agent
sudo systemctl enable --now parking-voice-agent-livekit-worker
sudo systemctl status parking-voice-agent
sudo systemctl status parking-voice-agent-livekit-worker
```

查看日志：

```bash
journalctl -u parking-voice-agent -f
journalctl -u parking-voice-agent-livekit-worker -f
```

## 配置 Nginx

```bash
sudo cp /opt/parking-voice-agent/deploy/tencent-cloud/parking-voice-agent.nginx.conf /etc/nginx/sites-available/parking-voice-agent
sudo sed -i 's/voice-agent.example.com/你的域名/g' /etc/nginx/sites-available/parking-voice-agent
sudo ln -sf /etc/nginx/sites-available/parking-voice-agent /etc/nginx/sites-enabled/parking-voice-agent
sudo nginx -t
sudo systemctl reload nginx
```

申请 HTTPS 证书：

```bash
sudo certbot --nginx -d 你的域名
```

## 验证

本机验证服务进程：

```bash
curl -s http://127.0.0.1:8000/health
```

公网验证：

```bash
curl -s https://你的域名/health
```

文本演示接口：

```bash
curl -s https://你的域名/demo/turn \
  -H 'content-type: application/json' \
  -d '{"caller_text":"你好，我叫张师傅，手机号是13800138000，车牌沪A12345，来找王经理送货"}'
```

## 更新发布

重复“上传代码”和“安装 Python 依赖”，然后重启服务：

```bash
sudo systemctl restart parking-voice-agent
sudo systemctl status parking-voice-agent
```
