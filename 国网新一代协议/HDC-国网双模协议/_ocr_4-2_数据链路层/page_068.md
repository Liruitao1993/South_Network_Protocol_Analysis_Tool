负载数据类型，含义如表112所示。

<div style="text-align: center;">表 112 负载数据类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>未携带负载数据</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>传播路径列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 513166 负载数据长度

路由请求报文所携带的负载数据的长度，可以为0。

## 513167 负载数据

路由请求报文所携带的负载数据的内容。当负载数据类型为 0x1 时，负载数据的内容格式如表 113 所示。TEI 表示路由请求报文转发过程中途经的站点。每途经一个站点，则传播路径列表中，多一组数据。通信成功率表示该站点与前一跳站点之间的上下行通信成功率。用百分比数值表示。信道质量表示该站点接收路由请求报文时，计算得到的信道质量。信道质量用原始信噪比数据表示。

<div style="text-align: center;">表 113 传播路径列表格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小</td></tr><tr><td rowspan="2">TEI0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信成功率0</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信道质量0</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td></tr><tr><td rowspan="2">TEIn</td><td style='text-align: center; word-wrap: break-word;'>n</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>n+1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>n+1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信成功率n</td><td style='text-align: center; word-wrap: break-word;'>n+2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信道质量n</td><td style='text-align: center; word-wrap: break-word;'>n+3</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr></table>

## 51317 路由回复报文

## 513171 路由回复报文格式

路由回复报文（MMeRouteReply）的格式定义如表114所示。

<div style="text-align: center;">表 114 路由回复报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由请求序列号</td><td style='text-align: center; word-wrap: break-word;'>14</td><td style='text-align: center; word-wrap: break-word;'>32</td></tr></table>