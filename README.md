# 外贸实用工具

**从 WhatsApp 询价到表格处理。** 九个工具，覆盖询价拉取、发票、询报价、运费、费用比较和现有表格修改。

[English](README.en.md) · [Jordan 的个人站](https://partstradeai.com/)

这是从我自己的外贸工作流里整理出的独立公开版。没有客户资料、真实价格、运价库、公司默认信息或密钥。所有样例都是虚构的；脚本在本地运行。WhatsApp 入口由你连接的 Agent 通过 MCP 读取指定对话和附件；翻译、需求判断及图片核对由 Agent 完成。使用云端模型时，工具读到的内容会提供给你选用的模型。

| 工具 | 能做什么 | 需要你提供什么 |
| --- | --- | --- |
| [WhatsApp 询价整理](skills/whatsapp-rfq) | 拉指定客户的询价及附件，核对更改和撤回，整理带图询价资料及待确认项 | 已连接的 WhatsApp MCP、客户线索和读取范围 |
| [发票与装箱单](skills/invoice-builder) | 商业发票、形式发票、货代用货值发票、装箱单 | 已确认的抬头、商品、数量、价格和条款 |
| [运费估算](skills/freight-estimator) | 按车型和零件筛选包装参考，再计算实重、体积重及费用 | 包装数据或有来源的包装记录、货代费率及规则 |
| [询价单翻译](skills/translate-rfq) | 修改 Excel 里的文字，保留原表图片、公式、样式和其他文件部分 | 原询价单及确认后的译文 |
| [带图供应商询价单](skills/supplier-rfq) | 带图供应商询价单，图片与商品放在同一行 | 已确认的需求和经过检查的参考图片 |
| [多车型报价单](skills/multi-quote) | 多车型、多品质报价单及汇总页 | 对外售价、明确选择的数量和运费 |
| [报价检查](skills/quote-audit) | 检查逐行金额、汇总、隐藏内容和内部字段提示 | 实际表格及明确的检查范围 |
| [Excel 局部修改](skills/xlsx-edit) | 在副本中修改已有文字或数量，核对其他文件部分保持一致 | 源文件、原值和目标值 |
| [门到门成本比较](skills/landed-cost) | 比较同一交货范围的门到门成本 | 完整费用及有来源的换算率 |

## 安装

需要 Python 3.10 及以上。表格生成与报价检查使用 `openpyxl`，图片使用 Pillow；文字翻译、局部修改和成本计算只使用 Python 自带功能。

```bash
git clone https://github.com/jordan-partstrade/trade-agent-skills.git
cd trade-agent-skills
python -m pip install -r requirements.txt
```

Codex 项目：把需要的完整 skill 文件夹放进 `.agents/skills/`。Claude Code 项目：放进 `.claude/skills/`。保留文件夹里的 `SKILL.md`、`scripts/` 和 `assets/`。其他 Agent 可直接读取说明，但安装目录可能不同。

可以这样请求：

> 用 invoice-builder，按这些已经确认的品名、数量和售价出商业发票。不要加入采购成本，核对最终金额。

> 用 freight-estimator，按这份货代费率和已包装尺寸估算运费。说明体积重、计费重及还未包含的费用。

> 用 translate-rfq，把这份西语询价单翻成中文。保留型号、零件号、数量、图片和公式，检查未翻译的文字。

## 从 WhatsApp 拉询价

已有 WhatsApp MCP 时，同时安装 `whatsapp-rfq` 和 `supplier-rfq`；收到客户 Excel 还需 `translate-rfq`。没有连接时，按[接入说明](skills/whatsapp-rfq/references/whatsapp-mcp.md)连接自己的账号，不用上传登录信息。

可以直接对 Agent 说：

> 用 whatsapp-rfq，把这个客户本轮询价拉出来。自己读取双方聊天、下载并查看相关图片，核对最新数量和取消的件；明确的需求生成带图供应商询价单，缺项单独列出来。先交付文件。

Agent 会调用 MCP 拉取真实材料，再生成本地资料包；无需你先复制聊天或手填商品信息。图片不能按位置猜对应，未知数量不会默填 1。明确行继续处理，待确认行和撤回行分别保留。

下面只演示**虚构 MCP 收据和虚构图片**的整理及表格生成，不会连接账号：

```bash
python skills/whatsapp-rfq/scripts/prepare_rfq.py examples/whatsapp-rfq.json --output out/whatsapp-demo
python skills/supplier-rfq/scripts/build_supplier_rfq.py out/whatsapp-demo/supplier-rfq.json --output out/whatsapp-demo/supplier-rfq.xlsx
```

样例将数量由 2 更正为 4 的前灯纳入询价，机油滤清器因缺数量留待确认，已取消的后视镜不纳入表格。原始聊天证据及待确认清单留在本地；共享前检查整理后的表格和图片，不要连同证据文件一起发送。

接入流程已按 WhatsApp MCP 的实际工具定义核对；仓库验证使用虚构收据，不代表已用真实客户对话完成验证。它不自动回复客户或联系供应商。

## 直接试用

下面的命令在仓库根目录运行。生成文件放在 `out/`，工具拒绝覆盖已有文件。

```bash
# 商业发票：演示货值 142.04 美元
python skills/invoice-builder/scripts/build_invoice.py examples/invoice.json --output out/commercial.xlsx

# 货代用货值发票：仅货值小计，不含运费和合计
python skills/invoice-builder/scripts/build_invoice.py examples/invoice.json --kind customs --output out/customs.xlsx

# 装箱单：不含价格，未提供的重量和尺寸留空
python skills/invoice-builder/scripts/build_invoice.py examples/packing.json --kind packing --output out/packing.xlsx

# 公斤计费演示：结果 69.35 美元，费率为虚构值
python skills/freight-estimator/scripts/estimate_freight.py examples/freight.json

# 海运演示：按立方米计算，示例最低计费 1 立方米
python skills/freight-estimator/scripts/estimate_freight.py examples/freight-sea.json

# 生成带图片、公式、多工作表和两种文字存储方式的演示询价单
python examples/make_demo_rfq.py out/demo-rfq.xlsx
python skills/translate-rfq/scripts/translate_xlsx.py extract out/demo-rfq.xlsx out/translations.json --glossary skills/translate-rfq/assets/es-zh-demo.json
# 补齐 translations.json 中空白的译文，再执行：
python skills/translate-rfq/scripts/translate_xlsx.py apply out/demo-rfq.xlsx out/translations.json out/rfq-translated.xlsx
```

词表示例会翻译五处文字，还有三个英文标签需要自行补齐。空译文保留原文字，并在结果中报告，不能据此声称整份已翻完。

![虚构数据生成的商业发票](docs/invoice-preview.png)

## 询报价、表格修改与费用比较

```bash
# 图片嵌入对应商品行，供应商报价栏留空
python skills/supplier-rfq/scripts/build_supplier_rfq.py examples/supplier-rfq.json --output out/supplier-rfq.xlsx

# 多车型报价：不同品质分别一行，零数量表示未选择；演示合计 155 美元
python skills/multi-quote/scripts/build_quote.py examples/multi-quote.json --output out/multi-quote.xlsx
python skills/quote-audit/scripts/audit_quote.py out/multi-quote.xlsx examples/quote-layout.json

# 修改已有数量：4 改为 6，原文件保持不变
python skills/xlsx-edit/scripts/edit_xlsx.py inspect out/multi-quote.xlsx --cell Compact E6
python examples/make_demo_edit.py out/multi-quote.xlsx --output out/edit-patch.json
python skills/xlsx-edit/scripts/edit_xlsx.py apply out/multi-quote.xlsx out/edit-patch.json --output out/quote-edited.xlsx

# 门到门费用：虚构演示比较 145 美元和 154 美元
python skills/landed-cost/scripts/compare_costs.py examples/landed-cost.json
```

![虚构参考图生成的供应商询价单](docs/supplier-rfq-preview.png)
![多车型报价单中的独立品质选择](docs/multi-quote-preview.png)

报价检查按明确的行、列和汇总范围核算；表格变动时要同步检查范围。它会提示隐藏内容、常见内部价格词、未完成文字和价格变动，但不能保证识别所有私人资料，也不能代替适配和价格协议确认。

局部修改会保留公式表达式，同时清空所有工作表的旧公式结果，并要求重新计算。**先用表格软件打开、重算和保存，再使用新合计。** 不允许修改公式格，不重建整张表，不覆盖原文件。

门到门比较只在全部方案费用齐全时选最低价。明确不适用的费用填零；未知填空或不填，结果会要求补资料。确认相同商品、数量、品质、目的地和税费口径，打包费用只算一次。

网站访客检查和通用 Agent 自验模板单独放在 [Agent 交接与验收工具库](https://github.com/jordan-partstrade/agent-handoff-review-verify)。

## 使用边界

### 运费估算先看车型与零件

SUV、轿车、MPV、皮卡等是车身类型；紧凑、中等、大型等是另一项尺寸分组。工具可根据你提供的车长、车宽分组，车高保留作背景信息。分组阈值是明示的内部参考规则，不是官方车型级别，也不是包裹尺寸。

包装数据优先于车型推测。同 OE 的唯一记录可直接作为估算参考；同车型、同平台或同车身类型及尺寸的大件记录，需要明确选择。相似尺寸只用于保险杠、机盖、车门、翼子板、风挡、长饰条等，传感器之类小件不会因为车更大就自动放大。

```bash
python skills/freight-estimator/scripts/prepare_shipment.py examples/vehicle-shipment.json --output out/prepared-shipment.json
python skills/freight-estimator/scripts/estimate_freight.py out/prepared-shipment.json
```

重复使用包装记录会标为“本次估算”，不会变成“本次实测”。缺少记录或无法确定用哪条时，工具不输出可计费输入，不忽略缺失商品。不猜车型参数，不自动合箱、折叠或套叠。演示车型和包装记录都是虚构数据。

### 文件与计算

- 发票按显示的两位小数单价计算，逐行四舍五入后相加。高精度单价合同需要另选工作流。拒绝内部成本等未支持字段；不会猜报关编码或申报值。
- 运费必须提供费率、来源和货代计费规则。缺少费率会报错。尺寸超限只提示，不代表承运许可或已经计算超长费。
- 询价单翻译只改文字所在的文件部分；其他部分逐个核对内容一致。原文件不修改，译文不能套到另一个或已变更的原表。
- 保留图片不等于翻译图片文字。批注、图表文字、公式结果不翻译；富文本按文字片段处理，需检查完整语义。
- 仅支持 XLSX。加密、签名、重复压缩成员及解压后超过 512 MiB 的文件会拒绝处理。输出磁盘需支持硬链接。
- 不发送客户消息，不订舱，不提交申报，不承诺适配、时效或最终费用。交付前检查实际表格。

## 验证与反馈

```bash
python -m pip install ruff Pillow
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

欢迎用[问题反馈](https://github.com/jordan-partstrade/trade-agent-skills/issues)提出需求。请用虚构或彻底匿名的输入，别上传客户资料、银行信息或密钥。

[MIT 开源许可](LICENSE)
