# AI Agent 面试项目深度复盘

## 1. 项目一句话介绍

这个项目是一个基于 `FastAPI + LangGraph + OpenAI-compatible LLM + Tavily` 的事实核查 Agent 服务。它的核心目标不是“返回一条搜索结果”，而是把用户输入拆成多个可核查 claim，再经过规划、正反检索、可选抓页、裁决和报告生成，输出一份结构化、可追踪、可持久化的核查结果。

如果用一句更适合面试的表达：

> 我做的是一个面向事实核查场景的多阶段 Agent 系统。它把一个开放输入拆成多个 claim，通过 LangGraph 管理状态机，在预算约束下做正反证据收集、内容抓取和结构化裁决，最后产出可审计的 Markdown 和 JSON 报告。

---

## 2. 这个项目为什么是 Agent，而不是普通问答或普通 RAG

### 2.1 和普通 LLM 问答的区别

普通 LLM 问答通常是：

1. 用户提问
2. 模型直接回答

这类系统的问题是：

- 不透明，用户不知道依据是什么
- 对最新信息不可靠
- 容易直接生成“像是真的”但不可核查的答案

这个项目做的是“先找证据，再给判断”，而不是“直接给答案”。

### 2.2 和普通 RAG 的区别

普通 RAG 更像：

1. 检索一些文档 chunk
2. 把 chunk 塞给模型
3. 让模型回答

这个项目比普通 RAG 多了几层控制：

- `claim decomposition`：先拆 claim，而不是整段文本直接检索
- `supervisor`：每轮判断下一步是继续搜索、切换 claim，还是结束
- `pro/con` 双向检索：刻意收集支持和反驳证据，降低单侧证据偏差
- `fetch`：对关键网页做正文抓取，补充 snippet 不够的信息
- `judgement schema`：要求模型输出结构化 verdict、confidence、best_sources、gaps
- `report schema`：最终输出结构化报告而不是自由文本

所以它更接近一个“带可控状态流转的 task-oriented agent”，而不是一个单次生成器。

### 2.3 为什么这个任务适合 Agent

事实核查天然适合 Agent，原因是它具备明显的多步骤特点：

- 要先理解任务
- 再拆问题
- 再规划检索
- 再选择是否继续搜索
- 再判断证据是否充分
- 最后输出报告

这类问题不是一个 prompt 就能稳定处理好的，特别是在你希望：

- 限制 token 成本
- 控制工具调用次数
- 保留中间状态
- 做失败恢复
- 对结果做审计

时，Agent 化是合理的。

---

## 3. 项目解决的核心问题

我实际在解决的是下面这几个问题：

1. 如何把一段自然语言输入转成多个可独立核查的 claim
2. 如何在预算有限的前提下收集足够证据
3. 如何避免只搜索到支持自己结论的材料
4. 如何让 LLM 输出结构化、可校验的判断
5. 如何把一条长时间运行的链路变成可以查询状态的服务
6. 如何把失败现场保存下来，方便调试和回放

---

## 4. 整体架构

### 4.1 目录结构

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
  webui/
    index.html
  api.py
  main.py
  routes.py
tests/
docs/
eval/
```

### 4.2 架构分层

可以把它理解成 6 层：

1. `API 层`
   - 对外暴露 HTTP 接口
   - 负责异步提交、同步执行、状态查询、UI 页面

2. `Service 层`
   - 负责一次完整 factcheck run 的生命周期
   - 负责后台任务排队和恢复

3. `Graph/Agent 层`
   - 用 LangGraph 编排状态机
   - 每个节点是一个清晰的职责单元

4. `Tool 层`
   - 搜索工具
   - 抓页工具

5. `Storage 层`
   - 把运行记录落盘成 JSON
   - 支持状态查询和任务恢复

6. `Presentation 层`
   - Markdown 渲染
   - 简单 Web UI

### 4.3 执行流

核心执行链路是：

```text
input_text
  -> extract_claims
  -> supervisor
  -> pro_planner
  -> con_planner
  -> pro_search
  -> con_search
  -> optional fetch_key_pages
  -> judge
  -> supervisor
  -> ...
  -> write_report
```

这是一个典型的“有限状态机 + LLM 决策点”的设计。

---

## 5. 技术栈与选择理由

### 5.1 FastAPI

用 FastAPI 主要因为：

- 天然适合 JSON API
- Pydantic 模型定义方便
- 测试和文档支持好
- 对原型和中小型服务足够高效

### 5.2 LangGraph

选择 LangGraph 而不是手写 while-loop 的原因：

- 有显式图结构，更容易表达状态迁移
- 节点和边界清晰，后续维护比“一个大函数里 if/else + while”更稳
- 更适合把 agent 行为拆成可测试单元

LangGraph 在这个项目里承担的是“有状态编排器”的角色，而不是魔法层。

### 5.3 OpenAI-compatible LLM

项目没有把模型强绑在某一家服务上，而是通过 `base_url + api_key + model_name` 去接兼容 OpenAI API 的服务。这样做的好处是：

- 模型供应商可替换
- 更适合实验不同模型
- 适合课程项目或原型快速试错

### 5.4 Tavily

Tavily 适合快速接入网页搜索，优点是：

- 返回结构化搜索结果
- 对检索型任务比较友好
- 适合事实核查的 web evidence 发现

但它不是最终答案。项目已经把搜索封装在 `tools/search.py`，所以后面可以换成：

- 自建搜索
- 混合检索
- RAG 数据库
- 其他 API

---

## 6. 状态设计

### 6.1 AgentState 的意义

`AgentState` 是整个图的共享状态，它定义了这个 agent 在运行时“记住什么”。

当前核心字段包括：

- `input_text`
- `claims`
- `claim_index`
- `active_claim_id`
- `work`
- `search_budget_remaining`
- `fetch_budget_remaining`
- `max_rounds_per_claim`
- `enable_fetch`
- `max_claims`
- `supervisor_plan`
- `pro_plan`
- `con_plan`
- `logs`
- `final_report`
- `final_markdown`
- `_model_name`
- `_llm_api_key`
- `_llm_base_url`

### 6.2 为什么 state 很关键

Agent 系统和普通函数式管道最大的区别之一，就是它往往需要跨多个步骤共享上下文。这个项目中 state 承担了：

- 工具调用结果累积
- 预算剩余量追踪
- 当前 claim 进度追踪
- 中间决策传递
- 最终输出承载

如果 state 设计不好，整个图就会变成一堆隐式耦合。

### 6.3 ClaimWork 的设计

每个 claim 还有自己的局部工作区：

- `rounds`
- `pro_sources`
- `con_sources`
- `judgement`

这样做的好处是：

- 不同 claim 的证据不会混在一起
- 可以单独统计每个 claim 跑了几轮
- 可以让报告生成时按 claim 聚合信息

### 6.4 为什么状态工厂单独抽出来

初始 state 不是在路由层手写，而是集中放到 `state_factory.py`。这是一个很重要的工程化细节，因为：

- API 调用和离线评测都能共用
- 参数覆盖逻辑集中管理
- 避免入口越来越多时状态初始化漂移

这是“把业务运行态初始化收口”的典型做法。

---

## 7. Graph 编排设计

### 7.1 为什么是图，而不是线性 pipeline

这个流程不是线性的，因为存在循环和条件分支：

- `supervisor` 可能决定继续搜索
- 也可能切换到下一个 claim
- 也可能直接结束
- `fetch` 也不是每轮都跑

因此它天然更像一个 graph，而不是直线。

### 7.2 route_from_supervisor

这个路由函数根据 `supervisor_plan.next_step` 决定：

- 去 `pro_planner`
- 继续 `supervisor`
- 去 `write_report`

这是“LLM 决策 + 程序路由”的典型组合。

### 7.3 route_after_con_search

这个路由函数决定：

- 如果允许抓页且还有抓页预算，就进 `fetch_key_pages`
- 否则直接 `judge`

这个设计说明：工具不是必须全部执行，而是根据上下文与预算做条件化执行。

### 7.4 为什么 graph 结构保持稳定很重要

在 Agent 项目里，一个常见坑是：

- 节点职责不清
- 路由条件散落在很多地方
- 一旦改流程就全局受影响

这个项目把路由逻辑集中在 `graph.py`，节点只负责“做事”，不负责“接线”，这会让后续迭代更稳。

---

## 8. 节点实现细节

### 8.1 extract_claims

#### 做什么

- 调 LLM 抽取 claim 列表
- 对 claim 做清洗和去重
- 初始化每个 claim 的 `ClaimWork`
- 设置第一个 `active_claim_id`

#### 工程细节

- 有 `_normalize_claim_text`
- 有 `_fallback_claims_from_input`
- 有 `_prepare_claims`

这意味着它不是“完全信任模型输出”，而是：

1. 先让模型结构化输出
2. 再做程序级清洗
3. 模型失败时还有兜底

#### 为什么要加 fallback

真实运行里发现，短中文输入时模型有时会返回空 claim。这个问题如果不修，整条链路会直接失效。

所以这里加入了：

- 如果 claims 为空
- 或 claim 文本清洗后为空
- 就直接从输入文本生成一个最小 claim

这类设计体现的是“agent 系统不能把所有可靠性都押在 LLM 上”。

### 8.2 supervisor

#### 做什么

决定当前 claim 下一步怎么走。

它会综合：

- 当前 claim 是否已有 judgement
- 当前 claim 已跑轮数
- 搜索预算是否耗尽
- 抓页预算是否还在
- 正反证据是否不足

然后输出一个 `SupervisorPlan`。

#### 为什么 supervisor 是核心

它相当于一个轻量 controller。Agent 不是“调用很多工具”就够了，关键是：

- 什么时候调用
- 是否还值得继续调用
- 什么时候停止

supervisor 就是在做这个“停止条件和下一步控制”。

#### 这里体现的 agent 思想

- `termination control`
- `budget-aware planning`
- `tool gating`
- `state-aware control`

这些都是 AI Agent 面试会重点问的点。

### 8.3 pro_planner / con_planner

#### 做什么

分别为“支持性证据”和“反驳性证据”生成搜索计划。

结构化输出包括：

- `query`
- `include_domains`
- `exclude_domains`

#### 为什么要正反双 planner

如果只搜支持证据，系统很容易：

- 搜到一堆同向材料
- 强化模型已有偏见
- 让最终 verdict 偏向单侧

双 planner 的价值在于主动制造“证据对抗面”。

这和信息检索里的 `confirmation bias mitigation` 很接近。

### 8.4 pro_search / con_search

#### 做什么

- 执行 Tavily 搜索
- 扣减搜索预算
- 结果去重
- 合并进对应侧的 evidence pool

#### 关键设计

- 每次搜索都消耗预算
- 搜索结果不是直接替换，而是追加并去重

这意味着系统具备“多轮累积式检索”的能力，而不是单轮覆盖。

### 8.5 fetch_key_pages

#### 为什么需要 fetch

搜索结果里通常只有：

- title
- url
- snippet

snippet 往往不够支持裁决。特别是：

- 数值型 claim
- PDF 报告
- 标题党页面

所以需要抓取正文。

#### 这层做了哪些升级

这一层现在已经不只是“拿 URL 然后 regex 抓一下 HTML”。

它支持：

- HTML 正文提取
- `text/plain`
- PDF 文本提取
- 内容质量过滤
- 持久化缓存
- claim-aware 优先级

#### claim-aware fetch 的意义

项目会对 claim 做粗粒度画像：

- 是否数值型
- 是否时效型
- 是否包含年份

然后根据来源特征加权选择最值得抓的页面。例如：

- 数值型 claim 更偏向 `report/data/statistics/pdf`
- 时效型 claim 更偏向 `news/press/update/announcement`

这其实是“把任务理解提前影响工具选择”的体现。

#### 为什么这很像 Agent，而不是普通爬虫

因为它不是机械抓所有 URL，而是在做：

- 信息价值估计
- 成本控制
- 工具调用优先级排序

这正是 agentic retrieval 的核心。

### 8.6 judge

#### 做什么

给当前 claim 输出结构化裁决：

- `verdict`
- `confidence`
- `rationale`
- `best_sources`
- `gaps`
- `suggested_followups`

#### 为什么用结构化输出很关键

如果直接让模型自由发挥，它可能：

- 漏字段
- 格式不稳定
- 证据引用混乱
- 结果难以下游消费

结构化输出的价值是把“开放生成”收紧成“可验证接口”。

#### 为什么还有 fallback best_sources

有时候模型会不返回 `best_sources`。这时系统会从 `pro_sources + con_sources` 中自动补一些回去。

这是一种典型的“LLM 不可靠，程序兜底”的设计哲学。

### 8.7 write_report

#### 做什么

把各 claim judgement 汇总成：

- `final_report`
- `final_markdown`

#### 关键设计点

1. 先把 sources 压薄
   - 避免上下文过长
   - 降低 structured output 失败概率

2. 如果结构化报告生成失败
   - 降级为纯 Markdown 文本报告

3. 如果 summary 里的数字和来源不一致
   - 再触发一个小的 rewrite 流程

#### 这里体现的高级点

这部分其实做了两层“输出质量控制”：

- 输出结构控制
- 输出事实一致性修正

即便 rewrite 还比较轻量，它已经体现出“LLM 输出不是一次生成结束，而是可以二次校正”的思路。

---

## 9. 模型调用与 Prompt 工程

### 9.1 模型封装

模型调用集中收口在 `llm.py`：

- `build_model`
- `invoke_structured`

这看起来很小，但工程意义很大：

- 避免节点里重复初始化
- 方便后续换 provider
- 方便统一 structured output 策略

### 9.2 为什么 structured output 是这个项目的核心能力

这个项目里至少有四类结构化输出：

- `ClaimsOutput`
- `SupervisorPlan`
- `SearchPlan`
- `Judgement`
- `FinalReport`

这说明系统不是让模型自由写散文，而是让模型在固定 contract 内输出。

面试里可以强调：

> 我会尽量把 LLM 放在“生成决策候选或结构化字段”的位置，而不是让它直接支配整个程序流。这样系统可控性更高，出错面更小。

### 9.3 Prompt 分层

prompt 没有和节点逻辑混在一起，而是拆进 `app/agent/prompts/`。

这个拆分的工程价值是：

- 节点逻辑更容易看
- prompt 可以独立迭代
- 后续做 A/B 测试更方便

---

## 10. 检索层设计

### 10.1 搜索结果为什么不能直接拿来用

原始搜索结果会有很多问题：

- URL 形式不同但实际上是同一页面
- 同域名结果过多，来源单一
- 低质量站点排名靠前
- snippet 太短或过于噪声

所以我做了 3 件事：

1. URL 规范化
2. 去重
3. 质量排序

### 10.2 来源评分

搜索层会对每条结果打启发式分数，参考因素包括：

- 是否命中 `include_domains`
- 是否是 `gov/edu/mil/int`
- 是否属于高信任站点
- 是否属于低信任站点
- URL 路径是否像 wiki/问答/聚合页
- 是否为 PDF
- snippet 长度是否足够
- snippet 是否出现 `official/study/report` 等信号词

这不是学习型排序器，但对事实核查原型来说很实用，因为：

- 成本低
- 解释性强
- 易于迭代

### 10.3 域名多样性

排序后不会简单取前 N，而是优先保留域名多样性，避免结果全部来自同一站点。

这体现的是检索里的 `source diversity` 思想。

### 10.4 搜索缓存

搜索结果会缓存到：

- `data/cache/search`

缓存 key 包括：

- query
- include_domains
- exclude_domains
- max_results

这样做的收益是：

- 降低重复请求成本
- 提高调试和重复实验速度
- 减少上游 API 波动对本地开发的影响

---

## 11. 抓页层设计

### 11.1 为什么抓页层重要

如果只有 snippet，很多 claim 是判不准的。抓页层解决的是“从搜索发现走向证据正文”的问题。

### 11.2 内容类型感知

抓页时不是假设所有 URL 都是 HTML，而是按 content type 分流：

- `application/pdf`
- `text/plain`
- 其他默认按 HTML

这是一个很典型的工程化细节。很多原型项目卡在这里，因为它们默认所有东西都是普通网页。

### 11.3 HTML 提取策略

HTML 处理做了几件事：

- 去掉 script/style/noscript/svg/canvas/form/iframe
- 去掉 nav/footer/header/aside
- 保留段落和块级元素换行
- 去标签
- 反转义 HTML entity
- 再做空白归一化

它不是一个完整阅读器，但作为轻量抽取已经足够支撑这个场景。

### 11.4 PDF 提取策略

引入 `pypdf` 后，抓页层支持 PDF。

当前策略是：

- 最多读前若干页
- 累积文本到一定长度就停止

这背后体现的是：

- 目标不是全文复刻
- 目标是拿到足够裁决的关键正文
- 必须控制 token 和耗时

### 11.5 质量过滤

抓到文本后还要再做过滤：

- 最小可见字符数
- 信号字符比例
- 英文词数或中文字符数门槛

这可以去掉：

- 只有菜单和按钮的页面
- 正文极少的壳页面
- 乱码页
- 信号很低的噪声页

### 11.6 抓页缓存

抓页结果缓存到：

- `data/cache/fetch`

抓页缓存比搜索缓存更重要，因为抓页更慢、更不稳定，也更依赖网络状态。

### 11.7 防重复抓取

每条 source 会记录：

- `page_fetch_attempted`

如果某个 URL 已经抓过但失败或被过滤，就不会在后续重复消耗抓页预算。

这体现的是“预算系统必须和失败状态耦合”，否则预算会被坏链接吃掉。

---

## 12. 报告生成设计

### 12.1 为什么最终要同时输出 JSON 和 Markdown

这两个输出面向不同消费者：

- `JSON` 面向程序
- `Markdown` 面向人

如果只有 Markdown：

- 不利于前端结构化展示
- 不利于后处理

如果只有 JSON：

- 可读性差
- 演示效果差

两者同时保留是很合理的。

### 12.2 为什么报告生成要做 source thinning

把所有证据原样塞给模型会导致：

- 上下文太长
- 结构化输出失败概率升高
- 报告质量不稳定

所以这里不是盲目“更多上下文更好”，而是做了适度裁剪。这体现了对 token budget 和模型稳定性的理解。

### 12.3 Markdown 降级策略

如果 `FinalReport` 结构化输出失败，系统会降级为普通 Markdown。

在面试里可以把这叫做：

- `graceful degradation`
- `structured-first, text-fallback`

这是一个很实用的生产思维。

---

## 13. 服务层与任务系统

### 13.1 为什么需要 service 层

如果把所有执行逻辑都放在路由里，会出现：

- HTTP 层和业务层耦合
- 评测脚本不能复用
- 单元测试难写

所以这里抽了 `factcheck_runner.py`。

它统一负责：

- 构建初始 state
- 调用 graph
- 维护 run 生命周期
- 成功和失败都持久化
- 返回统一结果对象

这就是典型的 `use case service`。

### 13.2 run 生命周期

一次 run 有明确状态：

- `queued`
- `running`
- `completed`
- `failed`

这是把“长链路 AI 调用”变成“可跟踪任务”的关键。

### 13.3 异步任务系统

`POST /check` 不是同步阻塞执行，而是：

1. 先生成 `run_id`
2. 先把状态保存成 `queued`
3. 后台 worker 排队执行
4. 客户端轮询 `GET /runs/{run_id}`

这个设计对真实前端体验很重要，因为 LLM + 搜索 + 抓页天然是长耗时任务。

### 13.4 为什么现在用进程内 worker

当前 worker 是单进程内线程方案，好处是：

- 简单
- 依赖少
- 原型阶段足够

坏处是：

- 不适合多实例横向扩展
- 不适合更复杂的并发调度
- 不适合分布式任务执行

如果进一步产品化，可以替换成：

- Celery + Redis
- RQ
- Dramatiq
- 基于数据库或消息队列的 job system

### 13.5 任务恢复

worker 启动时会扫描：

- `queued`
- `running`

且尚未 `finished_at` 的 run，把它们重新入队。

这意味着：

- 服务重启后不至于直接丢失未完成任务
- 有一定的 crash recovery 能力

这在 AI 应用里很实用，因为网络波动、模型 API 失败、服务重启都不罕见。

---

## 14. 持久化设计

### 14.1 为什么用 JSON 文件持久化

这个项目当前还没有引入数据库，而是把每个 run 落成 JSON 文件。

好处：

- 简单
- 直观
- 调试方便
- 非常适合课程项目和单机原型

缺点：

- 并发能力有限
- 查询能力弱
- 不适合大规模生产

### 14.2 RunRecord 保存了什么

包括：

- `session_id`
- `run_id`
- `status`
- `request`
- `response`
- `logs`
- `error`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

这套字段设计是比较完整的，因为它同时兼顾了：

- 运行审计
- 问题排查
- 状态查询
- 任务恢复

### 14.3 为什么“失败也落盘”很重要

很多 AI demo 的通病是：

- 成功有结果
- 失败只有 500

这会让调试非常痛苦。这个项目修掉了这个问题，失败也会保存：

- 失败类型
- 失败消息
- 中间日志
- 时间戳

这说明系统开始具备最基础的 observability 思维。

---

## 15. API 设计

### 15.1 核心接口

- `POST /check`
- `POST /check/sync`
- `GET /runs/{run_id}`
- `GET /sessions/{session_id}/latest`
- `GET /graph/mermaid`
- `GET /ui`

### 15.2 为什么同时保留 async 和 sync

异步接口适合前端和真实调用。

同步接口适合：

- 本地调试
- 单步验证
- 写脚本时快速拿结果

这体现的是“同一个业务能力，对不同使用场景暴露不同入口”。

### 15.3 Pydantic model 的作用

接口不是随便收一个 dict，而是通过：

- `CheckRequest`
- `CheckAcceptedResponse`
- `CheckResponse`
- `RunStatusResponse`

来约束输入输出。

这会显著降低：

- 前后端对接成本
- 参数漂移风险
- 文档和真实行为不一致的问题

---

## 16. Web UI 与启动脚本

### 16.1 为什么补了 UI

对于面试展示来说，只有 API 很难让人快速看到效果。一个简单 UI 可以显著提升：

- 演示体验
- 调试效率
- 展示完整度

### 16.2 UI 的实现方式

UI 很轻量：

- 不引入前端框架
- 直接用静态 HTML/CSS/JS
- 调异步 `/check`
- 轮询 `/runs/{run_id}`

这其实是很合理的取舍，因为：

- 这个项目的重点是 agent orchestration，不是前端框架
- 轻量页面更适合课程项目和原型

### 16.3 一键启动脚本

我额外做了 Windows 启动脚本，它会：

- 尝试多个 Python 解释器候选
- 自动启动 uvicorn
- 等服务真的 ready 之后再打开浏览器
- 把日志写到 `data/logs`

这个改动解决的是一个真实工程问题：用户双击脚本时，经常没有激活正确环境，导致浏览器先打开但服务根本没起来。

这个点在面试里可以体现：

- 我不是只写核心逻辑
- 我也会补使用链路和部署体验

---

## 17. 测试设计

### 17.1 测试覆盖范围

目前单测覆盖了：

- 配置读取
- state 初始化
- graph 路由装配
- runner 生命周期
- worker 恢复逻辑
- 搜索排序和缓存
- 抓页提取、缓存、过滤
- claim 提取 fallback
- fetch 优先级
- routes 契约
- UI 路由

### 17.2 当前测试状态

当前执行：

```powershell
python -m unittest discover -s tests -v
```

通过结果是：

- `32` 个测试通过

### 17.3 为什么这些测试有价值

AI 项目常见问题是：

- 只测 happy path
- 只做人工点点看
- 一改 prompt 就不知道哪里坏了

这里我尽量把非模型部分做成可测试逻辑，尤其是：

- 排序
- 去重
- 预算
- 路由
- 恢复
- fallback

这说明我在把 AI 系统拆成“可测试的经典工程单元”。

---

## 18. 真实验证做了什么

我不仅跑了单测，也跑了真实链路验证，包括：

- 应用能启动
- `/` 可用
- `/graph/mermaid` 可用
- 异步 `/check` 可提交流程
- 状态轮询正常
- 英文最小 claim 跑通
- 中文最小 claim 跑通
- HTML 抓页成功
- PDF 抓页成功

这很重要，因为 AI 项目里“单测绿了”不代表：

- 外部依赖可用
- 模型鉴权没问题
- 工具链真的能串起来

---

## 19. 项目中的关键工程决策

### 19.1 结构化输出优先

几乎所有关键节点都要求结构化输出，而不是自由生成。这样做是为了：

- 降低下游解析难度
- 提高行为稳定性
- 让 Agent 更可控

### 19.2 程序规则和 LLM 规则结合

项目不是“全靠 prompt”，而是：

- LLM 负责理解、规划、裁决
- 程序负责校验、去重、预算控制、缓存、fallback

这是比较成熟的 AI 工程思路。

### 19.3 显式预算系统

项目中明确有：

- `search_budget_remaining`
- `fetch_budget_remaining`
- `max_rounds_per_claim`

这几个量非常关键，因为现实里的 Agent 都会被这些约束：

- token 成本
- API 调用成本
- 时延

没有预算约束的 Agent 很容易变成一个“无限循环的高成本实验品”。

### 19.4 缓存优先

搜索和抓页都做了持久化缓存。这说明设计不是只关注正确性，也关注：

- 开发效率
- 重复实验成本
- 网络不稳定时的韧性

### 19.5 graceful degradation

项目里多处都有降级思路：

- claim 抽取失败 -> input fallback
- 结构化报告失败 -> Markdown fallback
- best_sources 缺失 -> 程序补齐

这类思路在 AI 系统中非常重要，因为 LLM 并不是稳定 deterministic 的组件。

---

## 20. 我在这个项目里体现出的 AI Agent 能力

如果面试官问“你在这个项目里体现了哪些 agent 相关能力”，我会归纳成下面这些：

### 20.1 Agent workflow design

我没有把问题做成单轮 prompt，而是设计了一个带状态流转的图式工作流，包括：

- 任务拆解
- 检索规划
- 工具调用
- 中间判断
- 报告生成

### 20.2 Tool orchestration

我做的不只是调用工具，而是设计了：

- 何时搜索
- 何时抓页
- 何时停止
- 哪个页面值得抓

### 20.3 Reliability engineering for LLM systems

我给多处关键节点补了：

- schema
- fallback
- cache
- persistence
- failure handling

### 20.4 State management

我把 agent 运行状态显式建模，并通过 LangGraph 管理状态迁移。

### 20.5 Retrieval quality optimization

我不仅接了搜索，还做了：

- ranking
- dedupe
- diversity
- claim-aware prioritization
- content filtering

### 20.6 Service productization

我把一个“能跑的 AI 原型”继续推进成了：

- 有 async API
- 有任务状态
- 有失败记录
- 有恢复机制
- 有 UI

这部分往往是面试里很加分的，因为它说明你不是只会调模型。

---

## 21. 相关知识延伸

这一部分是为了面试时往外扩展，不止停留在“我这个项目怎么写的”。

### 21.1 什么是 AI Agent

广义上，Agent 是一个：

- 能感知环境
- 能维护状态
- 能选择动作
- 能根据反馈继续决策

的系统。

在 LLM 时代，Agent 常见组成包括：

- LLM
- memory/state
- tools
- planner/controller
- execution loop

### 21.2 Agent 不等于“多调用几次模型”

一个真正有价值的 agent 系统至少要解决以下一项：

- 长任务分解
- 外部工具交互
- 多步状态控制
- 预算控制
- 环境反馈闭环

如果只是：

- 用户输入
- 调一次模型
- 输出答案

那更接近 chatbot，不一定是 agent。

### 21.3 多 Agent 和单 Agent 的区别

这个项目名义上是“多代理”风格，但更准确地说，它是“多角色节点”的图式系统：

- extractor
- supervisor
- planner
- researcher
- judge
- reporter

它不是多个真正独立进程 agent 在互相协作，而是一个共享状态下的多角色流程。

面试里如果被问到这个区别，可以直接说：

> 我更关注的是职责分离和流程稳定，而不是为了“多 agent”而多 agent。当前实现里，多角色节点已经足够表达这个任务，后续如果要做真正的多 agent 并行协作，再把角色拆成独立执行单元。

### 21.4 LangGraph 和 ReAct 的关系

ReAct 更像是一种 prompt pattern：

- Thought
- Action
- Observation

LangGraph 更像是执行框架：

- 定义节点
- 定义状态
- 定义边
- 控制循环和终止

这个项目更偏 LangGraph 式的显式工作流，而不是纯 ReAct。

### 21.5 为什么 structured output 很重要

structured output 的价值在 AI 工程里非常大，因为它相当于把 LLM 从“自由文本生成器”变成“弱类型函数”。

好处包括：

- 更容易接后端
- 更容易写测试
- 更容易做错误恢复
- 更容易控制流程

### 21.6 为什么需要 hybrid retrieval

如果后面接 RAG 数据库，最合理的不是完全替掉 web search，而是 hybrid retrieval：

- 内部知识库解决稳定背景知识
- web search 解决最新信息
- 官方 API 解决结构化事实

这三类信息源本质上是互补的。

### 21.7 事实核查为什么比问答更难

因为事实核查不是“生成一个看起来合理的答案”，而是要回答：

- 证据在哪里
- 证据是否足够
- 是否有反例
- 判断置信度如何
- 还缺什么

因此它天然要求：

- evidence grounding
- source attribution
- uncertainty handling

### 21.8 为什么需要 observability

AI Agent 系统很难调试，因为它不是纯 deterministic。你至少要看到：

- 当前状态
- 跑了哪些节点
- 用了哪些 sources
- 哪一步失败
- 输入输出是什么

这个项目已经迈出了一步，通过：

- `logs`
- `status`
- `saved_path`
- `error`
- `timestamps`

实现了基础可观测性。

### 21.9 生产化还缺什么

如果继续走向生产，通常还要补：

- 真正的任务队列
- 更强的 tracing
- metrics
- rate limit
- secret management
- retries with backoff
- circuit breaker
- 更系统的 evaluation
- 更细粒度权限与安全策略

---

## 22. 如果接入 RAG，我会怎么改

这个项目很适合接 RAG，但我不会暴力把 Tavily 替掉。

### 22.1 推荐方案

做成三类检索源：

1. `web retrieval`
2. `rag retrieval`
3. `structured api retrieval`

### 22.2 最小改造点

1. 新增 `app/tools/rag.py`
2. 在 `research.py` 里做合并检索
3. 扩展 `SourceItem`
   - `source_type`
   - `doc_id`
   - `chunk_id`
   - `score`
   - `metadata`
4. 让 `fetch` 只处理 `web` 类型来源
5. 对 `rag` 结果直接把 chunk 放到 `page_text`

### 22.3 为什么不建议只靠向量库

因为这个项目的一个目标是处理开放域、及时性强的 fact-check。单独向量库会面临：

- 数据不新
- 数据覆盖不全
- 事件类信息不足

所以更合理的是：

- `RAG for stable knowledge`
- `Web search for freshness`

---

## 23. 这个项目的不足与反思

面试里只讲优点不够，最好也明确说出边界。

### 23.1 当前不足

1. 任务系统还是单进程 worker
2. 搜索和抓页排序主要靠启发式
3. 没有完整的离线 benchmark dataset
4. 中文文案和 schema 里仍有历史编码痕迹
5. 报告质量仍然依赖 LLM 本身能力
6. 还没有真正的来源可信度知识库

### 23.2 我下一步会怎么做

1. 引入 hybrid retrieval
2. 做离线评测集和回归基准
3. 把 worker 换成真正的外部队列
4. 增加 metrics 和 tracing
5. 强化 judge/report 的 consistency check

这样的表达会让面试官觉得你知道系统还不完美，但你能清楚地定义下一步。

---

## 24. 面试时怎么讲这个项目

### 24.1 一分钟版本

> 我做了一个事实核查 Agent 服务。它基于 FastAPI 和 LangGraph，把输入文本拆成多个可核查 claim，然后通过 supervisor 控制多轮检索，在支持和反驳两个方向收集证据，再结合可选网页抓取做结构化裁决，最后生成 JSON 和 Markdown 报告。工程上我重点做了状态建模、预算控制、任务异步化、失败持久化、搜索与抓页质量优化，以及 32 个单元测试的覆盖。

### 24.2 三分钟版本

可以按这个顺序讲：

1. 为什么这个问题适合 agent
2. 整体 graph 怎么设计
3. supervisor 怎么控制流程和预算
4. 检索层和抓页层怎么做质量优化
5. 服务层怎么做异步任务、状态查询和失败恢复
6. 你做过哪些真实调试和鲁棒性修复

### 24.3 面试官最容易追问的点

1. 为什么不用一个大 prompt 一次完成
2. 为什么需要正反检索
3. 为什么选 LangGraph
4. 如何控制 agent 不无限循环
5. 结构化输出为什么更稳
6. 如何做评估
7. 如果接 RAG 怎么改
8. 如果生产化怎么改
9. 如何降低 hallucination
10. 怎么证明这个系统比单次 LLM 调用更可靠

---

## 25. 高频面试问答素材

### 25.1 你为什么说这是 Agent，而不是普通工作流

因为它不是固定线性管道，而是：

- 有共享状态
- 有多轮决策
- 有工具调用
- 有 supervisor 控制下一步行为
- 有预算和终止条件

### 25.2 你怎么控制 hallucination

我主要用 4 种方式：

1. 强制先收集证据再裁决
2. 正反双向检索，降低单侧证据偏差
3. 使用结构化输出，限制模型自由发挥
4. 对关键网页抓正文，而不是只信 snippet

### 25.3 你怎么处理 LLM 不稳定

我没有完全信任模型，而是加入了：

- fallback claim extraction
- fallback best_sources
- markdown fallback
- 失败落盘
- 缓存

### 25.4 你怎么做评估

当前主要是两类：

1. 工程层单测
2. 真实链路 smoke test

如果继续做，我会加：

- offline benchmark
- retrieval hit rate
- verdict accuracy
- citation correctness
- latency/cost metrics

### 25.5 你觉得这个项目最大的工程价值是什么

不是“调用了几个模型”，而是把一个不稳定、长耗时的 AI 链路做成了：

- 可编排
- 可测试
- 可追踪
- 可恢复
- 可展示

的服务。

---

## 26. 可以直接背的结论

### 26.1 技术总结

这个项目本质上是一个 `stateful, tool-using, budget-aware fact-checking agent`。

### 26.2 工程总结

我做的重点不是把 prompt 写长，而是把 LLM 放进一个可控的系统里：

- 结构化输出约束模型
- 显式 state 管理运行态
- graph 管理流程
- service 管理生命周期
- storage 管理审计和恢复
- tests 管理回归风险

### 26.3 面试总结

如果面试官只记住一句话，我希望他记住的是：

> 我不只是会调 LLM，我会把 LLM 变成一个能落地、能追踪、能迭代的 Agent 系统。

---

## 27. 复盘关键词

为了方便面试前快速扫一眼，可以记这些关键词：

- Claim decomposition
- Structured output
- LangGraph state machine
- Supervisor routing
- Budget-aware agent
- Pro / con retrieval
- Source ranking
- Fetch augmentation
- Claim-aware prioritization
- Graceful degradation
- Async task lifecycle
- Failure persistence
- Recovery
- Observability
- Hybrid retrieval
- Agent reliability

