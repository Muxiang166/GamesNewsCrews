# CrewAI 初版 Demo 归档

这个目录保存第一次联网测试使用的 CrewAI 顺序流版本，作为后续迁移 LangGraph 的对照样本。

包含内容：

- `main.py`：CrewAI 入口
- `config/agents.yaml`：旧版角色定义
- `config/tasks.yaml`：旧版任务定义
- `outputs/briefing.md`：本次生成的行业简报
- `outputs/social_pack.md`：本次生成的社媒内容包
- `初次运行结果.md`：终端完整打印日志
- `RUN_ASSESSMENT.md`：本次运行评分与问题复盘

未归档 `.env`、`.venv`、`__pycache__`，避免把密钥和本地环境带入 demo。

运行方式：

```powershell
Copy-Item .env.example .env
# 填写 DEEPSEEK_API_KEY 后：
python main.py
```
