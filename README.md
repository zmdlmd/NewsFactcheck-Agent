# FactCheck Multi-Agent

一个基于 `FastAPI + LangGraph + LLM + Tavily` 的多代理事实核查服务。

它的目标不是只返回一条搜索结果，而是把输入文本拆成多个可核查 claim，再经过规划、正反检索、可选抓页、裁决和报告生成，输出结构化核查结果。

![Graph](docs/assets/graph.png)

## 功能特点

- 多 claim 拆分：把一段输入文本拆成多个可独立核查的 claim
- Supervisor 驱动：按 claim 决定下一步是继续搜索、抓页还是进入下一个 claim
- 正反双向检索：分别收集支持和反驳来源
- 抓页增强：支持 HTML、纯文本和 PDF 抓取，并有缓存与质量过滤
- 任务式接口：支持异步提交、状态查询和同步兼容入口
- 结果持久化：保存 `queued/running/completed/failed` 生命周期数据
- 离线测试：当前已经补到 30+ 个单元测试

## 工作流

主流程大致如下：

1. 提取 claims
2. Supervisor 决定当前 claim 的动作
3. 分别生成 `pro` / `con` 搜索计划
4. 执行搜索并合并来源
5. 可选抓取关键页面正文
6. 裁决 claim
7. 生成最终报告

当前抓页层已经支持两类优先级增强：

- 通用来源质量排序
- claim 类型感知排序

其中：

- 数值类 claim 更偏 `report/data/statistics/pdf`
- 时效类 claim 更偏 `news/press/update/announcement`

## 项目结构

```text
app/
  agent/
    graph.py
    llm.py
    models.py
    render.py
    state.py
    state_factory.py
    node_handlers/
      planning.py
      research.py
      judgement.py
      reporting.py
    prompts/
  core/
    config.py
    logging.py
  services/
    factcheck_runner.py
    factcheck_tasks.py
  storage/
    sessions.py
  tools/
    search.py
    fetch.py
  api.py
  main.py
  routes.py
tests/
docs/
eval/
```

## 环境要求

- Python 3.10+
- 一个 OpenAI-compatible LLM 接口
- Tavily API Key

## 安装

### 使用 venv

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

### 使用 conda

```powershell
conda create -n factcheck-ma python=3.11 -y
conda activate factcheck-ma
python -m pip install -r requirements.txt
copy .env.example .env
```

## 配置

至少需要配置这些字段：

- `MODEL_NAME`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `TAVILY_API_KEY`

常用可选项：

- `MAX_CLAIMS`
- `SEARCH_BUDGET`
- `MAX_ROUNDS_PER_CLAIM`
- `ENABLE_FETCH`
- `FETCH_BUDGET`
- `SEARCH_CACHE_ENABLED`
- `SEARCH_CACHE_TTL_SECONDS`
- `FETCH_CACHE_ENABLED`
- `FETCH_CACHE_TTL_SECONDS`
- `FETCH_MAX_BYTES`
- `FETCH_MIN_TEXT_CHARS`
- `FETCH_MIN_TEXT_RATIO`
- `DATA_DIR`

示例见 [`.env.example`](.env.example)。

## 启动

项目会在启动时自动读取根目录 `.env`，并自动启动后台 factcheck worker。

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果你已经有固定解释器，也可以这样启动：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后可访问：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/ui`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/graph/mermaid`

### 一键启动 UI

Windows 下可以直接使用：

```powershell
.\start_ui.ps1
```

或者双击：

```text
start_ui.bat
```

脚本会：

- 自动选择可用 Python 解释器
- 启动 `uvicorn`
- 自动打开浏览器到 `/ui`

## API

### `POST /check`

异步提交任务，立即返回 `run_id`。

请求体：

```json
{
  "input_text": "请核查：地球围绕太阳公转。",
  "search_budget": 2,
  "max_rounds_per_claim": 1,
  "enable_fetch": true,
  "fetch_budget": 1,
  "max_claims": 1
}
```

典型响应：

```json
{
  "session_id": "s20260329_071630_255694",
  "run_id": "r20260329_071630_255694",
  "status": "queued",
  "saved_path": "data/sessions/.../run.json",
  "status_url": "/runs/r20260329_071630_255694"
}
```

### `GET /runs/{run_id}`

轮询任务状态，可能返回：

- `queued`
- `running`
- `completed`
- `failed`

### `POST /check/sync`

同步执行并直接返回最终结果。适合调试，不适合前端长时间阻塞调用。

### `GET /sessions/{session_id}/latest`

读取某个 session 最新一次运行记录。

### `GET /graph/mermaid`

返回当前 LangGraph 的 Mermaid 表达。

## 最小调用示例

### PowerShell

```powershell
$body = @{
  input_text = "请核查：地球围绕太阳公转。"
  search_budget = 2
  max_rounds_per_claim = 1
  enable_fetch = $true
  fetch_budget = 1
  max_claims = 1
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/check" `
  -ContentType "application/json" `
  -Body $body
```

### curl

```bash
curl -X POST "http://127.0.0.1:8000/check" \
  -H "Content-Type: application/json" \
  -d '{
    "input_text": "Fact-check this claim: Earth orbits the Sun.",
    "search_budget": 2,
    "max_rounds_per_claim": 1,
    "enable_fetch": true,
    "fetch_budget": 1,
    "max_claims": 1
  }'
```

## 测试

运行全部单元测试：

```powershell
python -m unittest discover -s tests -v
```

当前测试覆盖了：

- 配置读取
- graph 装配
- runner 生命周期
- 任务恢复
- 搜索排序与缓存
- 抓页提取、过滤与优先级
- 路由契约

## 数据与运行产物

默认情况下，项目会把运行和缓存写到 `data/`：

- `data/cache/search`
- `data/cache/fetch`
- `data/sessions`

这些内容已经在 `.gitignore` 中排除，不建议提交到仓库。

## 当前边界

- 任务系统目前是进程内 worker，适合本地和单实例部署
- 搜索和抓页优先级主要依赖启发式
- 还没有完整的离线评测数据集和回归基准
- 一些历史中文字符串仍有编码痕迹，后续还需要统一清理

## 进一步说明

详细的本轮迭代记录见 [`docs/iteration-summary-2026-03-29.md`](docs/iteration-summary-2026-03-29.md)。
