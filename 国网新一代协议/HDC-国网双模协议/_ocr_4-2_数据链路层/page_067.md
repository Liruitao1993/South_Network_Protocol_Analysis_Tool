<div style="text-align: center;">表110（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>芯片厂商</td><td style='text-align: center; word-wrap: break-word;'>ID 值</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x000F</td><td style='text-align: center; word-wrap: break-word;'>NR</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0010</td><td style='text-align: center; word-wrap: break-word;'>SL</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0011</td><td style='text-align: center; word-wrap: break-word;'>MT</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0012</td><td style='text-align: center; word-wrap: break-word;'>SI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0013</td><td style='text-align: center; word-wrap: break-word;'>RS</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0014</td><td style='text-align: center; word-wrap: break-word;'>XY</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0015 0xFFFF</td><td style='text-align: center; word-wrap: break-word;'>待扩展</td></tr></table>

## 51316 路由请求报文

## 513161 路由请求报文格式

路由请求报文（MMeRouteRequest）的格式定义如表111所示。

<div style="text-align: center;">表 111 路由请求报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由请求序列号</td><td style='text-align: center; word-wrap: break-word;'>14</td><td style='text-align: center; word-wrap: break-word;'>32</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路径优选标志</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>负载数据类型</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>负载数据长度</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>负载数据</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513162 版本

指路由修复算法版本号。该字段用于表示实时路由修复算法的演进版本。默认值为0。

## 513163 路由请求序列号

指一次路由修复请求的标识。路由请求序列号的生成规则为，2字节的业务报文原始源地址，加上业务报文的MSDU序列号。例如：

当某站点要转发的业务报文的 OSTEI 为 0x0118，MSDU 序列号为 0x2345，则针对该业务报文发起路由修复时，路由请求序列号为 0x01182345。

## 513164 路径优选标志

路径优选标志，在构成到达路由请求报文发起站点的路径时，该标志用于标识转发路由请求报文的当前站点是否具有优先被选择地位，即站点具有优先被选择地位时，转发的路由请求报文将携带该标志。

如果具有优选地位，则设置本标志为1，否则设置本标志为0。

## 513165 负载数据类型