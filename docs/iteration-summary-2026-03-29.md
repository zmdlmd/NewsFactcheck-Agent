# 2026-03-29 改动总结

## 概览

这一轮改动的目标不是只修一个点，而是把项目从“能跑的原型”推进到“结构更清晰、接口更稳、检索和抓页质量更可控”的状态。

本轮主要完成了 5 个方面：

1. 架构拆分与职责收口
2. 任务式接口与运行生命周期持久化
3. 搜索层质量控制与缓存
4. 抓页层升级、过滤与优先级策略
5. 测试补齐与真实运行验证

---

## 1. 架构拆分

### 1.1 拆分原来的 `nodes.py`

原来的 `app/agent/nodes.py` 同时承担了：

- LLM 初始化
- prompt 组装
- graph 节点逻辑
- state 更新
- 报告兜底处理

这一轮已经拆成按职责分离的结构：

- `app/agent/llm.py`
- `app/agent/state_factory.py`
- `app/agent/node_handlers/planning.py`
- `app/agent/node_handlers/research.py`
- `app/agent/node_handlers/judgement.py`
- `app/agent/node_handlers/reporting.py`
- `app/agent/prompts/`

结果是：

- graph 仍然只有一个编排入口
- 节点逻辑更容易单测
- prompt 和控制流不再混在一个大文件里

### 1.2 新增运行服务层

新增：

- `app/services/factcheck_runner.py`

作用：

- 统一构造初始 state
- 调用 graph
- 处理持久化
- 返回统一运行结果

这样 `routes` 和 `eval` 不再各自拼一套执行逻辑。

### 1.3 初始 state 构造收口

新增：

- `app/agent/state_factory.py`

作用：

- 用统一入口构造 graph 初始 state
- 集中管理 `search_budget`、`fetch_budget`、`max_claims`、模型注入字段等运行参数

---

## 2. 接口与任务执行模型

### 2.1 同步接口改为任务式提交

现在的接口结构是：

- `POST /check`
- `POST /check/sync`
- `GET /runs/{run_id}`
- `GET /sessions/{session_id}/latest`
- `GET /graph/mermaid`

其中：

- `POST /check` 负责异步提交任务
- `POST /check/sync` 保留同步兼容入口
- `GET /runs/{run_id}` 查询运行状态与结果
- `GET /sessions/{session_id}/latest` 查询最近一次运行

### 2.2 引入进程内 worker 和任务恢复

新增：

- `app/services/factcheck_tasks.py`

作用：

- 应用启动时启动单 worker
- 提交任务时先进队列再执行
- 启动时自动恢复 `queued` / `running` 状态的旧任务

当前这个 worker 仍然是单进程内方案，适合本地和单实例部署，不适合多 worker 横向扩展。

### 2.3 失败也会落盘

`app/storage/sessions.py` 已经扩展为保存完整生命周期字段：

- `status`
- `request`
- `response`
- `logs`
- `error`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

运行状态现在至少区分：

- `queued`
- `running`
- `completed`
- `failed`

这让排查失败请求不再只能看终端日志。

---

## 3. 配置与环境整理

### 3.1 修正配置读取时机

`app/core/config.py` 从导入时读取环境变量，改成了运行时读取。

这个改动解决了一个关键问题：

- `.env` 更新后，老的 `Settings` 不会继续使用旧值

### 3.2 补全配置项

当前配置已经覆盖：

- 模型参数
- 搜索预算
- 抓页预算
- 搜索缓存
- 抓页缓存
- 抓页质量阈值
- 数据目录

新增抓页相关配置：

- `FETCH_CACHE_ENABLED`
- `FETCH_CACHE_TTL_SECONDS`
- `FETCH_MAX_BYTES`
- `FETCH_MIN_TEXT_CHARS`
- `FETCH_MIN_TEXT_RATIO`

### 3.3 环境示例和 README 更新

已经更新：

- `.env.example`
- `README.md`

处理了两件事：

- 把新增配置写进示例和说明
- 去掉了示例文件里真实格式的 key 占位内容，改成普通占位值

### 3.4 依赖补充

`requirements.txt` 新增：

- `pypdf>=5.0`

用于 PDF 文本提取。

---

## 4. 主流程鲁棒性改进

### 4.1 claim 抽取兜底

`app/agent/node_handlers/planning.py` 已加兜底逻辑：

- 如果模型返回空 claims
- 或者返回 claim 为空白

则直接从输入文本生成最小可用 claim。

这解决了短中文输入时偶发 “0 claims” 的问题。

---

## 5. 搜索层升级

### 5.1 URL 规范化与去重

`app/tools/search.py` 现在会：

- 规范化 URL
- 基于规范 URL 去重
- 避免同源重复结果过多占位

### 5.2 来源质量排序

搜索结果增加了基于启发式的排序：

- 官方域名加权
- `gov/edu/int` 加权
- 高可信站点加权
- 低可信站点降权
- 低质量路径特征降权
- snippet 长度与可信词加分

同时抽出了可复用的：

- `score_source(...)`

它不仅用于搜索结果排序，也被后面的抓页优先级复用。

### 5.3 搜索缓存

新增持久化缓存目录：

- `data/cache/search`

缓存粒度包含：

- query
- include_domains
- exclude_domains
- max_results

目的：

- 降低重复检索成本
- 提升重复请求响应速度

---

## 6. 抓页层升级

### 6.1 抓页能力从简单 HTML 正则升级为内容类型感知流程

`app/tools/fetch.py` 现在支持：

- HTML 正文提取
- `text/plain` 文本解码
- PDF 文本提取
- 持久化缓存
- 大小限制
- 统一清洗和裁剪

新增缓存目录：

- `data/cache/fetch`

### 6.2 PDF 支持

引入 `pypdf` 后，抓页层可以对 PDF 做文本提取。

当前策略：

- 最多读取前若干页
- 限制总提取长度

目标是拿到足够裁决使用的正文，而不是完整文档全文。

### 6.3 抓页结果质量过滤

现在抓页文本不是“抓到就收”，而是先经过质量过滤：

- 最小文本长度
- 语言信号比例
- 英文词数或中文字符数门槛

这样可以过滤掉：

- 只有导航/按钮/菜单的页面
- 明显噪声页
- 几乎没有正文的壳页面

### 6.4 避免重复抓失败 URL

抓页节点现在会给来源写入：

- `page_fetch_attempted`

这意味着：

- 已经尝试过但被过滤或失败的 URL，不会继续反复抓取
- 抓页预算不会被同一个坏 URL 持续消耗

### 6.5 抓页优先级不再是“每边第一个”

`app/agent/node_handlers/research.py` 已把目标选择改为：

- 每边先选最值得抓的一条
- 再按全局质量补齐剩余额度

并且：

- 跨 `pro_sources` / `con_sources` 的重复 URL 只抓一次
- 抓到的 `page_text` 会回填到两边

### 6.6 claim 类型感知的抓页优先级

抓页优先级已经不只是通用来源分数，而会结合当前 claim 的类型：

- 数值类 claim 更偏 `report/data/statistics/pdf`
- 时效类 claim 更偏 `news/press/update/announcement`

当前是纯启发式实现，不增加额外模型调用成本。

---

## 7. 测试补齐

本轮新增或扩展了以下测试：

- `tests/test_config.py`
- `tests/test_factcheck_runner.py`
- `tests/test_factcheck_tasks.py`
- `tests/test_fetch.py`
- `tests/test_graph.py`
- `tests/test_planning.py`
- `tests/test_research.py`
- `tests/test_routes.py`
- `tests/test_search.py`
- `tests/test_state_factory.py`

覆盖范围包括：

- 配置读取
- state 初始化
- runner 生命周期
- 任务恢复与队列提交
- graph 节点装配
- claim 抽取兜底
- 搜索排序与缓存
- 抓页内容提取
- 抓页缓存
- 抓页质量过滤
- 抓页优先级
- 抓页失败不重试
- 路由返回契约

当前测试状态：

- `python -m unittest discover -s tests -v`
- 31 个测试全通过

---

## 8. 真实验证情况

这一轮不只是跑了单测，也做了真实链路验证。

已验证的内容包括：

- FastAPI 应用能启动
- `GET /` 可用
- `GET /graph/mermaid` 可用
- 异步任务提交和轮询状态可用
- 同步入口可用
- 最小英文 `/check` 可跑通
- 最小中文 `/check` 可跑通
- HTML 抓页可提取正文
- PDF 抓页可提取文本
- `node_fetch_key_pages` 的预算消耗和状态更新正常

说明：

- 运行时仍会出现 `langchain-tavily` 的 pydantic warning
- 这是第三方告警，不影响当前功能

---

## 9. 当前项目状态

经过这一轮改动后，项目已经具备以下特征：

- 代码结构比原来清晰很多
- API 不再只有同步长请求
- 失败请求可追踪
- 搜索和抓页有缓存
- 抓页不再盲抓低质量页面
- 抓页会按来源质量和 claim 类型做优先级选择
- 单元测试覆盖面已经能支撑后续继续迭代

仍然存在的边界：

- 任务系统仍是单进程内 worker
- 搜索与抓页优先级仍主要依赖启发式
- schema 和少量中文文案里仍有历史编码痕迹
- 还没有完整的离线评测数据集与回归基准

---

## 10. 下一步建议

下一步最值得继续做的方向有 3 个：

1. 把 claim 类型感知扩展到搜索规划阶段，而不只是抓页排序
2. 给 `judgement` 和 `reporting` 补更强的离线集成测试
3. 如果准备上线或多实例部署，把当前进程内 worker 换成真正的外部任务队列
