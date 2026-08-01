无线发现列表报文的统计序号，每次发送一个无线发送列表报文时，统计序号递增1，达到255后，环回为0。

## 513234 信息单元类型

用于指示信息单元内容，信息单元类型取值如表 124 所示。

<div style="text-align: center;">表 124 信息单元类型字段定义</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>站点属性信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>站点路由信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>邻居节点信道信息非位图版</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>邻居节点信道信息位图版</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 513235 长度类型

指示信息单元长度字段的位宽，长度类型取值如表 125 所示。

<div style="text-align: center;">表125 长度类型取值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>信息单元长度位宽为1字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>信息单元长度位宽为2字节</td></tr></table>

## 513236 信息单元长度

表示信息单元内容的长度，不包括信息单元类型、长度类型、信息单元长度的字段的内容。

## 513237 站点属性信息格式

表示站点的基本属性，站点属性信息格式如表126所示。

<div style="text-align: center;">表 126 站点属性信息格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CCO MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>0 5</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td rowspan="2">代理 TEI</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td rowspan="2">7</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>角色</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>层级</td><td rowspan="2">8</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>链路 RF 跳数</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理上行接收率</td><td style='text-align: center; word-wrap: break-word;'>9</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理下行接收率</td><td style='text-align: center; word-wrap: break-word;'>10</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>