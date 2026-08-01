## 513222 CCO MAC 地址

表示与本网络发生冲突的邻居网络的 CCO MAC 地址。

## 5 1 3 22 3 邻居网络个数

周边可见邻居网络的个数。

## 5 1 3 22 4 邻居网络条目

邻居网络信息，具体如表122所示。

<div style="text-align: center;">表122 邻居网络条目</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络（0）无线信道号</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络（1）无线信道号</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络（N）无线信道号</td><td style='text-align: center; word-wrap: break-word;'>N 1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

## 51323 无线发现列表报文

## 5 1 3 23 1 报文格式定义

无线发现列表报文（MMeRF DiscoverNodeList）格式定义如表 123 所示。

<div style="text-align: center;">表 123 无线发现列表报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点MAC地址</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>统计序号</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元1类型</td><td rowspan="2">7</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>7比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元1长度类型</td><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>1比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元1长度</td><td style='text-align: center; word-wrap: break-word;'>8/9</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1/2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元1内容</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元N类型</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>7比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元N长度类型</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>1比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元N长度</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1/2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息单元N内容</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513232 站点 MAC 地址

发送无线发现列表报文节点的 MAC 地址。

## 513233 统计序号