# HKUST CoursesDB

本目录独立运行，不导入或改动原有程序。Python 3.9+。

```bash
python3 -m venv BuildDB/.venv
BuildDB/.venv/bin/python -m pip install -r BuildDB/requirements.txt
BuildDB/.venv/bin/python -m BuildDB --term 2610
```

在项目根目录执行。默认输出 `BuildDB/CoursesDB_yyyymmdd.json`（香港日期）。指定文件：

```bash
BuildDB/.venv/bin/python -m BuildDB --term 2620 --output BuildDB/2620/CoursesDB_20260907.json
```

省略 `--term` 时，按香港日期估算当前学期，探测当前、后一个、前三个学期，打印结果，并优先选当前学期；不可访问则按上述顺序选择第一个可访问学期。9–12 月对应秋季、1 月冬季、2–5 月春季、6–8 月夏季；开学边界以显式 `--term` 为准。一次数据库只保存一个学期，避免不同学期同课号数据混合。

先打印 `.depts a.ug` 发现的完整学科列表，再依次请求每个学科（默认间隔 0.5 秒，有超时和重试）。每科后原子写入 `.partial.json`，最后建立反向关系并写正式文件。同日同名正式文件会在全部成功后替换。任何学科失败均返回退出码 1，保留部分文件，正式文件不变；重新运行可重试整个学期。

JSON 按“学科 → 无空格课号 → 课程数据”组织，例如 `db["ELEC"]["ELEC3400"]`。正式文件和部分文件均使用此结构；程序内部仍以课号索引，以便跨学科建立反向关系。每门课程包含：

- `Meta`：`Code`、`Title`、`Term`、`Description`、`Pre-requisite`、`Co-requisite`、`Exclusion`、`Credits`、`Consent`、`Quota`、`Enroll`、`Waitlist` 以及三种反向列表。
- `Data`：`Lecture`、`Tutorial`、`Labs`、`Research`、`Others`，各自以 L1、T1、LA1、R1 等节次名为键。节次包含 `Quota/Enroll/Avail/Waitlist`，Lecture 另含 `Instructor` 字符串数组，支持多位教师。
- `CC`：仅记录命中的 true，例如 `{"CC22":{"A":true},"CC26":{"UxOP-UROP":true}}`。支持网站的 `30-credit` 和 `30-cr` 两种写法。

人数为整数，页面缺失或 N/A 为 null；L 堂有未知数字时相应总计为 null，无 L 堂时总计为 0。不同上课时间的同一节次只计一次，移动端重复表格不计，专业配额弹窗不计入总人数。Credits 通常为数字，非单一数值则保留原文。

先修、同修、互斥字段保留原文。额外的 `Meta.Relations` 保存课程引用和布尔表达式（AND 优先于 OR，支持括号）。自然语言和无法完整解析的条件使用 `{"Text": 原文}` 保留，不猜测成绩、年级等要求。反向列表表示“哪些课程的对应条件中引用本课”，不表示所有 OR 分支都必须修读，也不自动推断互斥关系的对称性。未在当前学期出现的课程引用仍保留在 Relations，并打印到日志，不创建虚构课程条目。课程代码支持四字母学科加四位数字及字母后缀。

模块：`client.py` 网络与学期发现；`parser.py` 页面解析；`relations.py` 语义和反向引用；`storage.py` 原子存储；`__main__.py` 命令行流程。

```bash
BuildDB/.venv/bin/python -m unittest discover -s BuildDB/tests -v
```

`tests/fixtures/elec3400.html` 是用户提供的样例。`run_2610.log` 为端到端爬取记录。
