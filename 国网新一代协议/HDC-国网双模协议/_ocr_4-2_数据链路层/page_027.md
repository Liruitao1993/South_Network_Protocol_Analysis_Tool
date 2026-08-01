<div style="text-align: center;">图 9 SOF 帧物理块格式</div>


<div style="text-align: center;">表 37 物理块头的格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特数）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>序列号</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 5</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>帧起始标志</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>帧结束标志</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

## 5124 信标 MPDU 帧载荷格式

## 51241 物理块格式

无线信道载荷的物理块格式有6种，物理块的大小可选为16/40/72/136/264/520字节。信标帧支持40/72/136/264/520种物理块大小。载波信道载荷物理块格式有4种，物理块的大小为72/136/264/520字节，信标帧的载荷只支持一个物理块；缺省支持136/520字节的两种规格物理块格式，可选支持72/264字节的物理块格式。

物理块格式如图10所示。