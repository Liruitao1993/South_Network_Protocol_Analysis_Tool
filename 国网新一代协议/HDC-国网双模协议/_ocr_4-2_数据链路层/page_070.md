<div style="text-align: center;">表116（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小</td></tr><tr><td rowspan="2">TEIn</td><td style='text-align: center; word-wrap: break-word;'>n</td><td style='text-align: center; word-wrap: break-word;'>07</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>n+1</td><td style='text-align: center; word-wrap: break-word;'>03</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>n+1</td><td style='text-align: center; word-wrap: break-word;'>47</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信成功率 n</td><td style='text-align: center; word-wrap: break-word;'>n+2</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信道质量 n</td><td style='text-align: center; word-wrap: break-word;'>n+3</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr></table>

## 51318 路由错误报文

## 513181 路由错误报文格式

路由错误报文（MMeRouteError）的格式定义如表117所示。

<div style="text-align: center;">表 117 路由错误报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由请求序列号</td><td style='text-align: center; word-wrap: break-word;'>14</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>不可达站点数量</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>不可达站点列表</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513182 版本

指路由修复算法版本号。该字段用于表示实时路由修复算法的演进版本。默认值为0。

## 513183 路由请求序列号

指一次路由修复请求的标识。

路由错误报文中的该字段，使用对应的路由请求报文中的该字段值填充。

## 513184 不可达站点数量

不可达站点列表中站点的数量。

## 513185 不可达站点列表

表示从该站点无路由可达的站点列表。

每个地址占用2字节，表示不可达站点的TEI。

## 51319 路由应答报文

## 513191 路由应答报文格式

路由应答报文（MMeRouteAck）的格式定义如表118所示。