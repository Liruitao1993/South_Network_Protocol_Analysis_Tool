## 5 1 3 21 1 链路确认回应报文格式

链路确认回应报文（MMeLinkConfirmResponse）的格式定义如表120所示。

<div style="text-align: center;">表 120 链路确认回应报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>层级</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信道质量</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路径优选标志</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>7</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由请求序列号</td><td style='text-align: center; word-wrap: break-word;'>47</td><td style='text-align: center; word-wrap: break-word;'>32</td></tr></table>

## 513212 版本

指路由修复算法版本号。该字段用于表示实时路由修复算法的演进版本。默认值为0。

## 513213 路由请求序列号

指一次路由修复请求的标识。

链路确认回应报文中的该字段，使用对应的路由请求报文中的该字段值填充。

## 513214 层级

指发送链路确认回应报文的站点，在网络中所处的层级。

## 5 1 3 21 5 信道质量

表示该站点在接收对应的链路确认请求报文时，计算得到的信道质量。信道质量用原始信噪比数据表示。

## 513216 路径优选标志

路径优选标志，在构成到达路由请求报文发起站点的路径时，该标志用于标识转发路由请求报文的当前站点是否具有优先被选择地位。

如果具有优选地位，则设置本标志为1，否则设置本标志为0。

## 51322 无线信道冲突上报

## 5 1 3 22 1 报文格式定义

无线信道冲突上报报文（MMeRFChannelConflictReport）的格式定义如表 121 所示。

<div style="text-align: center;">表 121 无线信道冲突上报报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CCO MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>0 5</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络个数</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络条目</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>