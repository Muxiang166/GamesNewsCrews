# Games News Crew

多智能体游戏资讯采集、验证与简报系统。自动寻找 48 小时窗口内值得传播的游戏信息：官方硬新闻、高热玩家讨论、争议事件、权威流言、历史纪录类调味剂和梗图素材。

## 项目结构

```
Games_News_Crew/
  README.md                   # 本文件
  docs/                       # 项目文档
    roadmap.md                # 产品/工程路线图
    issues.md                 # 全局问题索引
    experience.md             # 运行经验与复盘
    toolchain_decision_matrix.md
    FastAPI/                  # FastAPI API 合约文档
    Vue/                      # Nuxt3 工作台指南
  LangGraph/                  # 当前核心项目
    main.py                   # 本地 IDE 入口
    README.md                 # LangGraph 包详细文档
    config/                   # 来源、质量、热度权重配置
    prompts/                  # LLM prompt 注册表
    harness/                  # 离线测试工具系统
    service/                  # FastAPI 内部工作台服务 (SVC-001~004)
    workbench/                # Nuxt3 内部工作台前端
    src/games_news_agent/     # Python 包
    tests/                    # 单元测试
    outputs/                  # 运行输出
  Demo/                       # 旧版 CrewAI 原型
  config/                     # 旧版 CrewAI 配置
  docs/                       # 项目文档
```

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+（仅工作台前端需要）
- DeepSeek API Key（可选，LLM 功能需要）

### 1. 安装

```bash
cd LangGraph
pip install -e .
```

### 2. 配置

在 `LangGraph/` 目录下复制并编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
GAMES_NEWS_DB_PATH=outputs/langgraph/mirror/games_news.db
```

### 3. 运行管道

```bash
cd LangGraph
python main.py
```

功能标志（按需启用）：
- `--run-llm-verifier`：LLM 声明验证
- `--run-llm-shadow`：LLM 影子模式（query compression、editorial judgment）
- `--run-search-expansion`：搜索扩展
- `--dry-run`：离线模式，从 harness 读固定候选

---

## 启动方式

### 方式 A：Trae / VS Code / 本地 IDE

#### FastAPI 服务

```powershell
# Windows PowerShell
cd LangGraph
$env:GAMES_NEWS_DB_PATH="outputs/langgraph/mirror/games_news.db"
uvicorn service.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# macOS / Linux (VS Code Terminal)
cd LangGraph
export GAMES_NEWS_DB_PATH="outputs/langgraph/mirror/games_news.db"
uvicorn service.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后访问：
- Swagger API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/v1/health

#### Nuxt3 工作台

```bash
cd LangGraph/workbench
npm install
npm run dev
```

访问 http://localhost:5173 ，工作台自动连接 `http://localhost:8000` 的 FastAPI。

#### 运行测试

```bash
cd LangGraph
python -m pytest service/tests/ -v
```

---

### 方式 B：Linux 服务器部署

#### 1. 环境准备

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip nodejs npm

# CentOS / Rocky / RHEL
sudo dnf install -y python3.11 python3.11-pip nodejs npm

# 创建虚拟环境
cd /opt/games-news-crew
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

#### 2. 安装项目

```bash
cd /opt/games-news-crew/LangGraph
pip install -e .
pip install fastapi uvicorn
```

#### 3. 配置环境变量

```bash
# 创建 .env 文件
cat > /opt/games-news-crew/LangGraph/.env << 'EOF'
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
GAMES_NEWS_DB_PATH=/opt/games-news-crew/LangGraph/outputs/langgraph/mirror/games_news.db
EOF
```

#### 4. FastAPI 服务 — systemd 托管

```bash
# 创建 systemd service 文件
sudo tee /etc/systemd/system/games-news-api.service << 'EOF'
[Unit]
Description=Games News Crew - FastAPI Workbench API
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/games-news-crew/LangGraph
Environment=PATH=/opt/games-news-crew/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=GAMES_NEWS_DB_PATH=/opt/games-news-crew/LangGraph/outputs/langgraph/mirror/games_news.db
ExecStart=/opt/games-news-crew/.venv/bin/uvicorn service.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable --now games-news-api.service

# 查看状态
sudo systemctl status games-news-api.service
# 查看日志
sudo journalctl -u games-news-api.service -f
```

#### 5. Nuxt3 工作台 — 静态生成 + Nginx

```bash
# 安装依赖并构建
cd /opt/games-news-crew/LangGraph/workbench
npm install
NUXT_PUBLIC_API_BASE_URL=http://your-server-ip:8000 npm run build

# 生成的静态文件在 .output/public/
# 用 Nginx 托管
sudo tee /etc/nginx/sites-available/games-news-workbench << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    # Nuxt3 静态文件
    root /opt/games-news-crew/LangGraph/workbench/.output/public;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # 代理 API 请求到 FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/games-news-workbench /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

#### 6. 可选：Nginx 反向代理（前后端统一域名）

如果不想分开部署前后端，可以用 Nginx 把所有请求代理到对应的服务：

```bash
sudo tee /etc/nginx/sites-available/games-news << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /opt/games-news-crew/LangGraph/workbench/.output/public;
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Swagger 文档
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host $host;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8000/redoc;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_set_header Host $host;
    }
}
EOF
```

#### 7. 定时运行管道

```bash
# 每 2 小时运行一次管道
crontab -e
# 添加：
0 */2 * * * cd /opt/games-news-crew/LangGraph && /opt/games-news-crew/.venv/bin/python main.py >> /var/log/games-news-cron.log 2>&1
```

#### 8. 验证部署

```bash
# API 健康检查
curl http://localhost:8000/api/v1/health

# 运行列表
curl http://localhost:8000/api/v1/runs

# 跑测试
cd /opt/games-news-crew/LangGraph
.venv/bin/python -m pytest service/tests/ -v
```

---

## API 端点一览

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/runs` | 运行列表 |
| GET | `/api/v1/runs/{id}` | 运行摘要 |
| GET | `/api/v1/runs/{id}/stories` | 故事列表 |
| GET | `/api/v1/runs/{id}/candidates` | 候选列表 |
| GET | `/api/v1/runs/{id}/notifications` | 通知列表 |
| GET | `/api/v1/runs/{id}/artifacts` | 工件索引 |
| GET | `/api/v1/runs/{id}/artifacts/{key}` | 工件内容 |
| GET | `/api/v1/runs/{id}/quality-flags` | 质量标记 |
| POST | `/api/v1/runs/{id}/human-reviews` | 提交人工评审 |
| GET | `/api/v1/runs/{id}/human-reviews` | 列出评审 |

详细 API 文档：http://localhost:8000/docs

---

## 安全

- 所有数据访问通过 `persistence/agent_query.py` 白名单查询
- SVC-004 只读安全 Guard：阻挡路径穿越、任意 SQL、发布动作
- 文件读取以 `artifact_manifest` 为白名单
- 写操作仅限于人工评审记录，不修改事实/排名/平台草稿

## 文档索引

- [LangGraph 包详细文档](LangGraph/README.md)
- [API 合约](docs/FastAPI/api-contract.md)
- [Nuxt3 工作台指南](docs/Vue/workbench-guide.md)
- [产品路线图](docs/roadmap.md)
- [全局问题索引](docs/issues.md)
- [工具链决策矩阵](docs/toolchain_decision_matrix.md)
