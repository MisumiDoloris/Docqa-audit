# docqa-audit

给「文档 → 检索 → 生成」这条流水线做验收的小工具。

它不生产回答，也不接模型。它只回答一个问题：**这套东西现在能不能交付**，如果不能，错在哪一层。

## 为什么要有它

做文档问答的人，绝大多数只验最后一步：端到端答对了就算过。这有三个盲区。

第一个，答对可能是蒙的。检索没找到，模型拿常识补了一句，刚好是对的。

第二个，答错也定位不到。端到端八十分，不知道是解析把表拆了、是切块切断了答案、还是生成时编了个数字。

第三个，没有人给输入做体检。PDF 解析出来的 Markdown 看着挺像样，合并单元格丢了、表头串行了、整列空了，这些错很安静，一路传到检索和生成。

所以这里拆成三层，各查各的，各给结论。**端到端满分不算过，三层各自要过。**

## 三层各查什么

**解析层** 吃解析器（Docling、MinerU、Marker 之类）吐出来的 Markdown，不绑具体工具，换解析器不用改代码。查的是一张表里列数不一致、表头有空列、整列为空、空格子比例过高。

**检索层** 读切块和人工出的题，算 hit@k 和 MRR。标准答案块由人定，脚本只打分。给了多组排位数据就分层出指标，能直接看出是哪一层掉的分。

**生成层** 把生成文本里的数字、编号、日期挑出来，逐个回原文找锚点，找不到就标出来。年限类直接拦，数字类降一档让人眼过。

## 怎么跑

只依赖标准库，clone 下来直接跑：

```bash
python3 -m docqa_audit run --config demo/config.json
```

看 `demo/report.md`，里面是仓库自带的一份示例数据，故意埋了三个问题：一张表列数不一致、一道题重排后丢了、一个数量是编的。

跑测试：

```bash
python3 -m unittest discover -s tests -v
```

退出码：0 是能交付，1 是有拦的条目，2 是配置有问题。

## 配置

```json
{
  "project": "项目名",
  "parse": {"file": "parse/parsed.md"},
  "retrieval": {
    "chunks": "chunks/chunks.jsonl",
    "questions": "questions/questions.jsonl",
    "ranking": "retrieval/ranking.jsonl",
    "ks": [1, 3, 5]
  },
  "claims": {"answer": "generation/answer.md", "source": "source/source.txt"},
  "out": "report.md"
}
```

路径相对配置文件所在目录。哪一层不想跑就整段删掉。

`ranking` 可以不写，不写就用内置的关键词重叠打分跑个基线出来，报告里会标成「内置基线」。真要用还是得自己给排位。

## 底座怎么接

解析层不自己解 PDF，它吃别人吐出来的 Markdown。所以底座是插上去的，写在 `docqa_audit/adapters/` 里：

```bash
.venv/bin/pip install "markitdown[pdf]"                  # 默认底座，MIT，纯 python，无 OCR
.venv/bin/python -m docqa_audit convert --pdf 某文件.pdf --out demo/parse/real.md
```

- **markitdown**：默认。快、依赖小、电子版 PDF 够用。它管不了扫描件。
- **docling**：可选，`--tool docling`。版面与表格更准，带 OCR，适合扫描件。

检索侧也是一个底座，默认 **rank_bm25**：

```bash
.venv/bin/pip install rank_bm25
.venv/bin/python -m docqa_audit rank --chunks chunks.jsonl \
    --questions questions.jsonl --out ranking.jsonl -k 10
```

配置里写 `"ranker": "bm25"` 且不给 `ranking` 文件，`run` 会当场算一遍排位，不用先生成文件。

**中文切词这里用了汉字二元组**（「合格证编号」切成 合格/格证/证编/编号），不引分词库。糙但稳，零额外依赖。代价是它认不出「合格证」是一个词，同义改写会丢分。要更好就接 jieba 或自己的词表，接口不用改，换 `tokenize` 就行。

**装 Docling 踩过的四个坑，都写进 `scripts/install_cpu_docling.sh` 了，照着跑能一次过。**

1. PyPI 上那支 torch 轮子是 CUDA 版，装的时候会拖 nvidia-cudnn / cublas / triton 好几个 G，装完 `import torch` 还要找 `libcublasLt.so`，找不到就炸。必须用 `download.pytorch.org/whl/cpu` 的 `+cpu` 轮子，196MB，实测本机直连这个域名是通的，不用代理。
2. torchvision 也得是 `+cpu` 那支。混用会报 `operator torchvision::nms does not exist`，ABI 对不上。
3. `transformers` 5.x 在这个组合下炸在 `AutoImageProcessor`，降到 4.x。
4. HuggingFace 默认走 Xet 传输，国内镜像返 401。跑转换要带 `HF_HUB_DISABLE_XET=1 HF_ENDPOINT=https://hf-mirror.com`。

## 同一个文件，两个底座，两种结论

示例 PDF 分别用两个底座解，再拿同一把尺子量：

| 底座 | 解析出来的样子 | 解析层结论 |
| --- | --- | --- |
| markitdown | 表头合成「序号 名称」一格，第一行被切成两行，一列全空 | 不可交付（拦 1 警 2） |
| docling | 六列对齐，每行内容各归各位 | 通过 |

这张表就是这套工具存在的理由。底座好坏不该靠感觉，拿尺子量，量完把差异摆出来给人看。

## 路线（2026-10-18 定）

按顺序做，一步一晚，做完一步提交一次。

1. **检索层接真排位**，用 rank_bm25（纯 python，几兆）。现在那个词重叠打分只是让 demo 跑得起来的兜底。
2. **生成层加软判据**，DeepEval 当壳，**RAGAS 的指标组挂进去**当一个可选包。默认关闭，开了才跑。
3. **硬判据永远优先**：回源校验给结论（拦／警），模型裁判只出参考分，不参与能不能交付的判断。
4. **门面**：MIT LICENSE、GitHub Actions 跑那套测试。

两条要提前知道的代价：

- **成本与可复现性**：DeepEval 和 RAGAS 的核心指标都要叫模型当裁判，要 key、要钱，同一个答案跑两次分数可能不一样。所以它们是参考层，不是判决层。
- **遥测**：DeepEval 默认上报使用数据（posthog）。要关掉得设 `DEEPEVAL_TELEMETRY_OPT_OUT`，这条要写进文档，别人 clone 下来不该被默默上报。

## 审查：怎么发现这套东西自己有 bug

测试绿不等于对。测试可能只是摆设，或者根本没覆盖到关键判断。所以这里有一个破坏实验。

```bash
.venv/bin/python scripts/mutation_check.py          # 全跑
.venv/bin/python scripts/mutation_check.py --only M5
```

做法：把代码里的关键判断故意改坏（比如把「列数不一致就拦」改成「永远不拦」），跑测试。
测试必须变红。改坏了还是绿，说明那条测试是空壳，或者那段代码没被覆盖。
每个变异体跑完都会从备份还原，并用 sha256 核对还原是否成功；基线测试本来就不绿时直接中止。

**约定：每次跑之前先问，跑完交三样 —— 结果、过程、影响因素。** 这条是使用者的要求，写在文档里是为了别忘。

### 这个实验证明不了什么

- 变异体是作者自己挑的，挑的都是自己知道有测试覆盖的地方。所以 7 个全被杀，只说明这 7 处有反应，说明不了覆盖之外的地方对不对。
- 它只验「测试有没有反应」，不验「规则能不能抓到真错」。后面那件事只能在真实资料上验。
- 示例数据只有 6 个切块 5 道题，过拟合风险很高。真数据上的指标一定会掉，掉多少才知道规则有多虚。

## 几条定死口径

**不打分。** 分数会让人以为九十分就能用。这里只判能不能交付，拦的条目一出现就是不能。

**标准答案人定，判卷脚本做。** 出题的不能判自己出的卷，模型更不行。

**数字必须带边界和单位。** "5 台" 不能在 "550mm" 或 "3.5m3" 里找到锚点，那是两个不同的数。

**去空格和留空格要用两份原文。** 比编号去空格，比数字留空格。删了空格，"1001" 和 "1台" 会粘成 "10011台"，本来对得上的数会被判成编造。这条有回归用例。

## 已知限制

- 解析层只查结构，不判断内容对不对。表里把"3台"写成"5台"，这一层看不出来，那是生成层和人工的活。
- 内置基线是很朴素的词重叠，只能证明"能跑"，不能当检索质量结论。
- 生成层只认中文工程写法里的数字、编号、日期，英文语境和自由文本还没覆盖。
- 没做多语言，没做并发，没做增量。

## 验收标准（已定，2026-10-18）

这三条是使用者的判断，不是作者的判断。定完之后每一层的 verdict 就照这个走。

1. **解析层：列数不一致直接拦。** 这份文档是归档给人看的，结构错了就是错了，不降档。
2. **检索层：只看相对变化，不看绝对值。** 检索质量的绝对线没有行业基准，定一条线就是编数。所以基线取第一层（一般是改动前的排位），其余层只报 ΔMRR 和 Δhit@1，变差就报。
3. **生成层：数字标红放行，年限拦。** 数字回源失败只标红，不拦整段，但必须有人看过；年限类仍然直接拦，因为那是最容易被查穿的一类。

## 目录

```
docqa_audit/
  model.py            Finding / LayerResult / verdict
  auditors/
    parse_audit.py    解析层
    retrieval_audit.py 检索层
    claim_audit.py    生成层
  report.py           拼报告
  config.py           读配置
  cli.py              命令行
demo/                 示例数据（虚构）
tests/                回归用例
```
