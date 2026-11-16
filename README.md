# Token Phrase Corpus

Python 3.11 标准库实现的预分词资料字面检索。文档和查询已经分词；项目不负责分词、大小写折叠或 Unicode 归一化。

## 公开 API

`from tokenphrase import Corpus, Document, find_spans`

- `Corpus(documents)`：输入 ID 到词元 list/tuple 的 Mapping。ID 和每个词元均须为非空字符串；每篇文档至少一个词元，空文档集合合法。词元可含空格，始终作为一个不可拆分的词元。非法输入抛 ValueError。
- 构造时复制词元并固定文档集合。`corpus.documents` 是按 Python 字符串升序排列的 Document 元组；Document 的 id 和 tokens 只读，tokens 为元组。`Document(id, tokens)` 同样验证并复制 list/tuple。
- `corpus.find(query)`：query 是非空字符串词元组成的非空 list/tuple。返回全部 `(doc_id, start, end)`，按 ID、start、end 升序。端点为从零开始的原文词位置，左闭右开；保留重叠，无命中返回 []。仅逐词完全相等才匹配，不能跨文档。返回列表由调用者独立持有。
- `find_spans(tokens, query)`：同样校验文档和查询，返回一个文档内全部 `(start, end)`，按起点升序。
- `corpus.get(doc_id)`：返回不可变原文词元元组；非法 ID 抛 ValueError，未知合法 ID 抛 KeyError。
- `corpus.evidence((doc_id, start, end))`：返回对应原文词元元组，也接受三项列表。任何合法非空原文区间均可取证，无需先调用 find。端点必须为非布尔 int 且满足 `0 <= start < end <= 文档长度`；形状、ID 或区间非法抛 ValueError，未知合法 ID 抛 KeyError（先查 ID，再验证端点）。

例如 `Corpus({"d": ["a", "a", "a"]}).find(["a", "a"])` 返回 `[("d", 0, 2), ("d", 1, 3)]`。样例中的“心肌 梗死”与“心梗”只分别匹配其字面词元。

实现每次对全部原文扫描，没有持久索引；设原文总词数为 N、查询词数为 Q，最坏匹配时间 O(NQ)，Corpus.find 不含最终返回值的额外空间为 O(Q + H)，H 为单篇文档的最大命中数（构造时另有 O(N) 文档快照）。不包含改写规则、别名展开或改写检索。

## 运行

```sh
python3.11 -B verify.py
python3.11 -B demo.py
```

verify 发现并运行 tests 下完整原回归，包含独立逐区间参照的确定性小序列穷举、原文取证交接、输入校验、不可变性和文档边界核验。demo 输出真实查询结果及其原文证据。无需安装、网络、数据库或临时文件；命令只读取本项目。
