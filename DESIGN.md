# 交付说明：多词改写编译器与规则检索视图

本文说明 REWRITES.md 两项联动能力的实现、公开表示的读取方式、编译与检索之间的
不变量、搜索状态与原文边界归属，以及编译表示的规模上界。仅使用 Python 3.11 标准库。

## 1. 模块与公开 API

| 模块 | 职责 |
| --- | --- |
| `tokenphrase/rewrites.py` | 能力 A：公开改写编译器。只依赖 `model.token_tuple` 做词元校验，不导入 Corpus。 |
| `tokenphrase/rules.py` | 能力 B：`RuleView`。只调用 `rewrites` 的公开函数/字段，不自行实现任何规则匹配。 |
| `tokenphrase/corpus.py` | 新增 `Corpus.with_rules(rules)`；原字面 `find/get/evidence` 语义与代码路径不变。 |

公开导出（`from tokenphrase import ...`）：

- `compile_rewrites(tokens, rules) -> CompiledRewrites`
- `CompiledRewrites`：字段 `source_tokens`、`rules`、`boundaries`、`edges`、`adjacency`；
  方法 `recognizer(start, end) -> TokenNFA`、`span_edges(start, end)`
- `RewriteEdge`：只读字段 `start, end, output, kind, rule, rule_index, is_identity`
- `TokenNFA`：只读字段 `n_states, start, accept, adjacency, transitions, source_start, source_end`；
  方法 `boundary_at(state)`、`is_accept_state(state)`、`accepts(sequence)`
- 通用自动机算法 `product_reachable(nfa1, nfa2)`、`languages_intersect(nfa1, nfa2)`
- `validate_rules(rules)`：规则校验与独立去重快照
- `Corpus.with_rules(rules) -> RuleView`，视图方法 `find(query)`

## 2. 编译表示（能力 A）

### 2.1 切分 DAG

设原文词数为 n。编译结果是一张以**原文位置**为节点的有向无环图：

- 边界节点 `0..n`（`boundaries`），边界 i 位于词 i-1 与词 i 之间；
- 每个原文词 i 有一条恒等边 `i -> i+1`，输出 `(tokens[i],)`，`kind="identity"`；
- 对每条规则 `(lhs, rhs)` 与每个满足 `tokens[i:i+len(lhs)] == lhs` 的位置 i，
  加入规则边 `i -> i+len(lhs)`，输出整个 rhs，`kind="rule"`，并记录 `rule` 与
  `rule_index`；
- 边的标签只是输出词元，**不会再长出任何边**。因此替换产生的词不可能再次匹配规则，
  生成词不再改写，天然保证“一次解释只改写原始词段”、无递归；
- 每条边消费一个非空连续原文片段，同一路径上的边互不重叠，正好对应一次合法切分。

**完整解释 = 从边界 s 到边界 e 的一条路径**；路径上各边输出按原序拼接，就是该解释
产生的词序列。一个 `[s, e)` 区间的全部完整解释，恰好等于规范中“切分 + 逐片段保留或
整段替换”产生的全部解释，不多也不少。

### 2.2 边界正确性（不能进/出替换内部，不能串接互斥分支）

- 规则边从边界直接跳到边界，替换内部不存在任何节点：不可能从替换中间起步，也不可能
  在替换内部结束。
- 互斥的规则选择是同一对边界之间的不同边；路径每一步只选择其中一条，边的输出整体
  消费，无法把两条互斥边的输出各取一段再串接。
- `recognizer(s, e)` 只收录满足 `edge.start >= s` 且 `edge.end <= e` 的边，因此区间外
  的边不会泄漏进区间解释。规范允许逐区间重编译，本实现为每个区间即时构建公开 NFA，
  其语言与整篇 DAG 上受限于该区间的路径完全一致。

### 2.3 公开 NFA（TokenNFA）

`CompiledRewrites.recognizer(start, end)` 返回该区间输出语言的公开 NFA：

- 状态 `0..(e-s)` 是**边界状态**，逐一对应原文坐标；其余为私有链状态，用于物化
  多词输出（rhs 有 k 个词时引入 k-1 个链状态）；
- 每条迁移恰好消费一个词元，无 epsilon 迁移；
- 唯一接受状态是边界状态 `e-s`，链状态永远不是接受状态；
- `boundary_at(state)`：边界状态返回其原文坐标，链状态返回 `None`——这就是检索器
  判断“终点是否为合法原文边界”的公开依据；
- `accepts(sequence)` 用状态集上的多项式成员测试，不枚举路径。

独立读者可以只凭 `edges/adjacency` 复核接受路径：沿边界边逐段走到接受边界，读各边
`output` 即得到一条完整解释；`tests/test_rewrites.py` 的独立参照正是自行枚举切分与
规则选择后，与公开 NFA 的全部接受序列做精确集合对照。

### 2.4 规模上界（多项式，不保存展开文本）

设 n 为原文词数，R 为去重后规则数，`L = 规则左部总词数`，`M = 规则右部总词数`，
P 为实际规则匹配位置数（`P <= R*n`）：

- 恒等边 n 条、规则边 P 条；编译结果边数 `n + P = O(nR)`，每条边只保存一个 rhs
  引用/元组，全部边右部词元总量 `O(n + P*M/R)` 量级，整体为
  `O(n + P*M)`（不保存任何展开后的完整解释）；
- 单个区间 NFA：状态数 `<= (e-s) + 1 + P_span*(最大右部长-1)`，
  即 `O(n + P*M)`；迁移数 = 所有收录边的输出词数之和，同阶；
- `CompiledRewrites` 本体（不含逐区间 NFA）为 `O(n + P + L)` 量级的图加上规则快照
  `O(L+M)`；以题目给定的量（原词数、规则总词数、匹配位置对应右部词数）表述，均为
  多项式有界。

## 3. 规则检索视图（能力 B）

### 3.1 快照与隔离

`Corpus.with_rules(rules)` 经 `validate_rules` 校验并复制为元组快照（精确重复的
`(lhs, rhs)` 去重，重复规则不改变可接受解释集合；首次出现顺序保留）。调用后再修改
调用方的规则列表不影响视图；原 Corpus 不被修改。空规则集合法，此时视图结果与字面
`find` 一致（回归中专门核验）。

### 3.2 命中判定（只消费 A 的公开结果）

`RuleView.find(query)`：

1. 按原查询约定校验 query（非法抛 ValueError）；
2. `compile_rewrites(query, rules)`，取查询整体的公开 NFA `Q`；
3. 对每篇文档 `compile_rewrites(tokens, rules)`；对每个起点 s 取
   `recognizer(s, 文档末尾)` 得文档 NFA `D_s`；
4. 调用公开的 `product_reachable(Q, D_s)`：在两个 NFA 的状态积上同步相同词元标签，
   返回可达积状态集合。这是通用自动机操作，不含任何规则知识；
5. 对每个可达积状态 `(q, d)`，当 `q` 是 Q 的接受状态且 `d` 是 `D_s` 的**边界状态**
   （`boundary_at(d)` 非空）时，命中原文区间 `(doc_id, s, boundary_at(d))`；
6. 全部命中放入集合去重（同一区间经多条解释只返回一次，重叠区间全部保留），按
   ID、start、end 排序返回；坐标始终是原文半开词坐标，不跨文档。

积可达非空于接受对，当且仅当两个 NFA 存在一条共同接受的词序列，即：**查询的一条
完整解释与某个非空原文区间的一条完整解释逐词相等**。检索器不读取编译器私有状态，
也不另行实现规则匹配；编译器不接收 Corpus、不裁决命中集合。

### 3.3 搜索工作量与“不枚举展开文本”

- 设查询 NFA 状态数 S_q、文档区间 NFA 状态数 S_d，单次积构造最坏
  `O(S_q * S_d * t_q * t_d)`（t 为单状态迁出度），与“接受路径条数/解释条数”无关；
- 一篇 n 词文档构建 n 个起点 NFA，总工作量对 n、S_q、右部总词数为多项式；
- 分支链 `["a"]*n` + 规则 `a -> b` 有 2^n 条完整切分路径，但编译只有 2n 条边、
  NFA 只有 n+1 个状态和 2n 条迁移；不匹配查询的积状态数仅为线性小量
  （`tests` 与 `demo.py` 均记录实测值），不存在对 2^n 条解释或其展开文本的枚举。

### 3.4 原文证据归属

命中坐标全部来自 DAG 边界，`Corpus.evidence(hit)` 不经任何改写直接切原文元组，因此
返回的永远是该区间完整的原始词段（高亮保持完整原文，不会拼出原文中不存在的短语）。
别名“心梗”命中 `("心肌","梗死")` 区间时，evidence 返回 `("心肌","梗死")`。

## 4. 编译与检索之间的交接不变量

1. **图即语义**：区间 `[s,e)` 的完整解释集合 = DAG 上 s 到 e 的路径输出集合 =
   `recognizer(s,e)` 的语言，三者恒等。
2. **边界封闭**：NFA 接受状态与 `boundary_at` 可识别的状态恰好是原文边界；替换内部
   只有链状态，`boundary_at` 返回 `None`，检索器绝不会把内部位置当作终点。
3. **单向、一次**：边只从原文边界出发且标签不再生边；无递归、无删除、无空输出。
4. **两侧同规则集**：查询与文档用同一快照编译；共同接受词序列是命中的唯一条件。
5. **去重保重叠**：命中按区间去重，重叠区间保留；排序键与字面接口一致。
6. **字面不变**：`Corpus.find/find_spans/evidence/get` 与原回归字节级保留，规则视图
   是独立对象；空规则视图等价于字面检索。
7. **快照独立**：编译结果与视图都复制输入容器；后续外部修改不影响已构造对象。

## 5. 校验行为

- `compile_rewrites` 的 tokens 沿用 `token_tuple`：非空 list/tuple、每项非空字符串，
  非法抛 ValueError；
- 规则须为 list/tuple，每项为二元 `(lhs, rhs)`，两侧均为非空字符串的非空序列，
  非法抛 ValueError；
- 视图 `find` 的 query 校验与原 `Corpus.find` 完全一致；
- `recognizer/span_edges` 的端点须为非布尔 int 且 `0 <= start < end <= n`，否则
  抛 ValueError。

## 6. 验证与演示入口

- `python3.11 -B verify.py`：unittest 发现 `tests/` 下全部测试。原 `test_literal.py`
  未改动（8 个测试）；新增 `test_rewrites.py`（19 个测试），包含：
  - REWRITES.md 全部可核对样例与医疗别名端到端证据；
  - 独立短例参照：自行枚举切分与规则选择，对查询和每个原文区间生成解释集合，做
    NFA 语言精确集合对照和命中列表/证据对照（确定性穷举 + 固定种子随机 fuzz）；
  - 互斥分支、替换内部边界、重叠规则、方向性、非递归、双侧改写、变长输出、同区间
    多解释去重、恒等/重复/空规则、快照隔离、输入校验；
  - 分支链资源核验：2^n 解释下的边/状态/迁移数与积搜索实测工作量断言。
- `python3.11 -B demo.py`：先输出与原演示同构的字面报告，再输出别名规则报告
  （含每个命中的完整原文证据），最后输出分支链资源报告。
