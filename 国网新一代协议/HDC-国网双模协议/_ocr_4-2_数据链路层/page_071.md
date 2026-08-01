<div style="text-align: center;">表 118 路由应答报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>13</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由请求序列号</td><td style='text-align: center; word-wrap: break-word;'>47</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

## 513192 版本

指路由修复算法版本号。该字段用于表示实时路由修复算法的演进版本。默认值为0。

## 513193 路由请求序列号

指一次路由修复请求的标识。

路由应答报文中的该字段，使用对应的路由请求报文中的该字段值填充。

## 51320 链路确认请求报文

## 513201 链路确认请求报文格式

链路确认请求报文（MMeLinkConfirmRequest）的格式定义如表119所示。

<div style="text-align: center;">表 119 链路确认请求报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由请求序列号</td><td style='text-align: center; word-wrap: break-word;'>14</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>确认站点数量</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>确认站点列表</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513202 版本

指路由修复算法版本号。该字段用于表示实时路由修复算法的演进版本。默认值为0。

## 513203 路由请求序列号

指一次路由修复请求的标识。

链路确认请求报文中的该字段，使用对应的路由请求报文中的该字段值填充。

## 513204 确认站点数量

需要进行链路确认站点的数量。

## 513205 确认站点列表

表示需要进行链路确认的具体站点的列表。

每个站点占用2字节，表示确认站点的TEI。

## 51321 链路确认回应报文