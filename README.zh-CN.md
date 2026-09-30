# 外贸 Agent Skills

**把重复的表格工作交给工具。** 发票、运费估算、保留图片和格式的询价单翻译。

[English](README.md) · [Jordan 的个人站](https://partstradeai.com/)

这是从我自己的外贸工作流里整理出的独立公开版。没有客户资料、真实价格、运价库、公司默认信息或密钥。所有样例都是虚构的；脚本在本地运行，不调用 AI 服务。翻译内容由你或你使用的 Agent 提供。

| 工具 | 能做什么 | 需要你提供什么 |
| --- | --- | --- |
| [invoice-builder](skills/invoice-builder) | 商业发票、形式发票、货代用货值发票、装箱单 | 已确认的抬头、商品、数量、价格和条款 |
| [freight-estimator](skills/freight-estimator) | 按车型和零件筛选包装参考，再计算实重、体积重及费用 | 包装数据或有来源的包装记录、货代费率及规则 |
| [translate-rfq](skills/translate-rfq) | 修改 Excel 里的文字，保留原表图片、公式、样式和其他文件部分 | 原询价单及确认后的译文 |

## 安装

需要 Python 3.10 及以上。发票工具和演示表生成器需要 `openpyxl`，另外两个脚本仅使用 Python 自带功能。

```bash
git clone https://github.com/fzy476598462-afk/trade-agent-skills.git
cd trade-agent-skills
python -m pip install -r requirements.txt
```

Codex 项目：把需要的完整 skill 文件夹放进 `.agents/skills/`。Claude Code 项目：放进 `.claude/skills/`。保留文件夹里的 `SKILL.md`、`scripts/` 和 `assets/`。其他 Agent 可直接读取说明，但安装目录可能不同。

可以这样请求：

> 用 invoice-builder，按这些已经确认的品名、数量和售价出商业发票。不要加入采购成本，核对最终金额。

> 用 freight-estimator，按这份货代费率和已包装尺寸估算运费。说明体积重、计费重及还未包含的费用。

> 用 translate-rfq，把这份西语询价单翻成中文。保留型号、零件号、数量、图片和公式，检查未翻译的文字。

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

欢迎用[问题反馈](https://github.com/fzy476598462-afk/trade-agent-skills/issues)提出需求。请用虚构或彻底匿名的输入，别上传客户资料、银行信息或密钥。

[MIT 开源许可](LICENSE)
