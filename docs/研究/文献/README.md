# 文献

上游研究的原始材料。PDF 是引用依据，`.md` 是可检索的抽取或转录版本。

| 文件 | 出处 |
|---|---|
| `szczepanczyk-2023-jie-pseudocode-and-algorithms.pdf` / `.md` | Szczepanczyk, M. (2023). *Journal of Information Economics* 1(3), 15. doi:10.58567/jie01030004 |
| `hahnel-szczepanczyk-weisdorf-2020-simulation-experiments-slides.pdf` / `.md` | Hahnel、Szczepanczyk、Weisdorf，Systems Science Noon Seminar，2020-12-04 |

两份的下载地址：

```sh
curl -sSL -o szczepanczyk-2023-jie-pseudocode-and-algorithms.pdf \
  http://www.szcz.org/img/jie-paper-2023.pdf
curl -sSL -o hahnel-szczepanczyk-weisdorf-2020-simulation-experiments-slides.pdf \
  https://thenextrecession.wordpress.com/wp-content/uploads/2021/01/computersimulationexperimentsofparti_powerpoint.pdf
```

## 两份文本版本的可信度不同

- **JIE 论文的 `.md`**：pypdf 6.10.2 从文字层逐字抽取，内容完整，排版与图表位置与原文不同
- **幻灯片的 `.md`**：原 PDF 的文字层损坏（字间空格被吃掉），内容为逐页人工转录。
  转录可能有误，以 PDF 为准

## 版权

两份都由作者或会议方公开发布。若本仓转为公开仓库，发布前需确认许可条款——
JIE 由 Anser Press 出版，多为开放获取，但要逐份核实。

## 未取得的材料

| 材料 | 状态 |
|---|---|
| Hahnel (2021) *Democratic Economic Planning* 第九章 | 图书，非公开。幻灯片称完整结果在此 |
| AEA 2021 年会论文 | 会议页面有条目，未找到公开全文 |
| ZNetwork 访谈视频 | 未处理 |
