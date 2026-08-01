## 5 1 1 3 15 MAC 地址标志

MAC地址标志字段，用于指示MAC帧头中是否携带MAC地址，含义如表9所示。

<div style="text-align: center;">表9 MAC 地址标志</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>未携带 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>携带 MAC 地址</td></tr></table>

## 5 1 1 3 16 组网序列号

组网序列号是一个8比特的字段，表示当前组网的序列号。该值为顺序递加的值，CCO每次重新组网后都需要加1。

## 511317 MSDU 类型

MSDU类型字段用于指示MSDU帧的类型，如表10所示。

<div style="text-align: center;">表10 MSDU类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>网络管理消息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1 47</td><td style='text-align: center; word-wrap: break-word;'>数据链路层待扩展</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>48</td><td style='text-align: center; word-wrap: break-word;'>应用层报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>49</td><td style='text-align: center; word-wrap: break-word;'>IP 报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>待扩展</td></tr></table>

## 5 1 1 3 18 原始源 MAC 地址

原始源MAC地址是48比特字段，指最初产生MSDU帧的站点MAC地址。该字段只有在“MAC地址标志”字段值为1时存在。原始源MAC地址不能为FF FF FF FF FF；00 00 00 00 00 00为非法地址。

## 5 1 1 3 19 原始目的 MAC 地址

原始目的MAC地址是48比特字段，指MSDU帧的最终目的站点MAC地址。该字段只有在“MAC地址标志”字段值为1时存在。

## 5 1 1 4 单跳 MAC 帧头格式

## 51141 帧头格式

单跳MAC帧头格式如表11所示。单跳MAC帧仅用于无线信道。

<div style="text-align: center;">表 11 单跳 MAC 帧头格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td rowspan="2">0</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>