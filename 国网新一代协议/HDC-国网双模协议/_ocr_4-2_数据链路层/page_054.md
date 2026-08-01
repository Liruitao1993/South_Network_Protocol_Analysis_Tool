表示发起代理变更站点与新代理之间通信链路类型，链路类型值定义如表86所示。

<div style="text-align: center;">表86 链路类型值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>高速载波链路</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>无线链路</td></tr></table>

## 51367 代理 TEI

表示申请代理变更站点的新代理站点的TEI。

## 51368 子站点数

表示申请代理变更站点的所有子站点的数目。

## 51369 端到端序列号

表示端到端的报文序列号。请求代理变更的站点，在产生代理变更请求报文时，需要获取一个序列号，CCO在确认代理变更时，需要在代理变更请求确认报文中携带代理变更请求报文中的端到端报文序列号。

## 513610 路径序号

表示路径通知序列号。在代理变更请求确认报文中，会携带路由路径信息。每次代理变更请求确认报文的发送，CCO会获取一个路径通知序列号，获取的路径序列号是递加的。代理站点或者STA站点，在刷新路由表项时，需要判断路径序列号是否为最新的。

## 513611 子站点条目

包含子站点信息，即代理变更请求发起站点的所有子站点的TEI，定义如表87所示。

<div style="text-align: center;">表87 子站点条目</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td rowspan="2">TEI[0]</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12</td><td rowspan="2">子站点的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr><tr><td rowspan="2">TEI[1]</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12</td><td rowspan="2">子站点的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>子站点的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>TEI[N 1]</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>子站点的 TEI\nN=子站点数</td></tr></table>

## 5137 代理变更请求确认报文（位图版）

## 51371 代理变更请求确认报文（位图版）格式