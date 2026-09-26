# 研究

对既有实现的复现与审查。这些结果是本库设计决策的依据，也是 v1 的验证目标。

| 文件 | 内容 |
|---|---|
| [复现记录.md](复现记录.md) | 重跑上游已发表实验，冷启动与热启动的迭代轮数，性能实测 |
| [上游代码问题.md](上游代码问题.md) | `pequod-plus` 与 `pe_ifb_compute` 的正确性、性能与工程状态问题 |
| [文献/](文献/README.md) | 上游研究原文的出处与下载地址 |
| [wiod-字段映射.md](wiod-字段映射.md) | 把 WIOD 装进 `Economy` 会缺什么，阶段 2 定差额前的输入 |
| [同类实现对照.md](同类实现对照.md) | 三个公开的经济计划实现：形式化、数据模型、许可证边界，以及 dep1ex 上的第一次跨机制对照 |

## 对象

| 仓库 | 说明 |
|---|---|
| `msszczep/pequod-plus` | 当前实现，Clojure + SQLite。clone 在 `upstream/pequod-plus/` |
| `msszczep/pequod-cljs` | 产出已发表结果的实现，ClojureScript。仓库 1 GB，未 clone |
| `msszczep/pe_ifb_compute` | 研究计算需求的仓库，Python |
| `msszczep/pequod-clj`、`pequod2` | 更早的实现，Clojure 与 NetLogo |

上面五个是同一套模型的历代实现。另有三个**互不相关的**经济计划实现，
形式化与数据模型都不同，clone 在 `upstream/` 下，见 [同类实现对照.md](同类实现对照.md)：
`ssamot/socialist_planning`、`epournaras/EPOS`、`pablovegan/Economic-Planning`。
三个都是 GPL，**只读不抄**。

同一套模型七年内被重写五次，跨四种语言，没有一次沉淀成可复用的库。
这是本项目的立项理由。

## 主要文献

原文的出处与下载地址见 [文献/](文献/README.md)。

- Szczepanczyk, M. (2023). Pseudocode and algorithms for computer simulations of
  democratically planned economies. *Journal of Information Economics* 1(3), 15
- Hahnel、Szczepanczyk、Weisdorf (2020-12-04). Computer Simulation Experiments of
  Participatory Annual Planning. Systems Science Noon Seminar。**冷启动与热启动的
  迭代轮数分别列在这里**，是目前唯一给出这个区分的公开材料
- Hahnel, R. (2021). *Democratic Economic Planning*. Routledge. 第九章。未取得
- 项目页 <https://participatoryeconomy.org/project/computer-simulations-of-participatory-planning/>

2023 年那篇论文末尾列了七条未来方向，逐条对应本库的功能：其他生产函数、改进价格调整算法、
环境影响、鲁棒性测试、人在环干预、议会间互动、与交互式规划软件结合。

其中第二条值得单独记：作者写明价格调整规则「was arrived at with little concerted effort」，
并打算在规则空间里做系统性搜索。那个搜索需要成百上千次运行，而上游一次实验四小时。
2020 年的幻灯片上已经写着「there's room for improvement here」，六年过去仍未做。
