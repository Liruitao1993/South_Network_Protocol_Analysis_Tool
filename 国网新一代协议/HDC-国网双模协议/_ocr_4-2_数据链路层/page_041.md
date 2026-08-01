表示发起关联请求的站点的MAC地址，长度为6字节。

## 51323 候选代理 TEI

包含了候选代理站点列表，最多支持携带5个候选代理站点的TEI。

## 51324 链路类型

表示发送关联请求站点与候选代理的通信链路类型，链路类型值定义如表61所示。

<div style="text-align: center;">表61 链路类型值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>高速载波链路</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>无线链路</td></tr></table>

## 51325 相线

表示本站点的所属相线的评估结果，最低比特位字段存放评估出的所属相线，其他字节依次填入可能的备选相位，相线的值定义如表62所示。

<div style="text-align: center;">表62 相线值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示未知相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>表示A相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>表示B相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>表示C相线</td></tr></table>

## 51326 设备类型

表示终端设备的类型，定义如表63所示。

<div style="text-align: center;">表63 设备类型字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>抄控器</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>集中器本地通信单元</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>电表通信单元</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>中继器</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>II 型采集器</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>I 型采集器单元</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>三相电表通信单元</td></tr></table>

## 5 1 3 2 7 MAC 地址类型

表示关联入网时使用的 MAC 地址的来源，定义如表 64 所示。