<div style="text-align: center;">表97 上行路由信息字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td></tr><tr><td rowspan="2">下一跳站点 TEI0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由类型 0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td></tr><tr><td rowspan="2">下一跳站点 TEI4</td><td style='text-align: center; word-wrap: break-word;'>8</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>9</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由类型 4</td><td style='text-align: center; word-wrap: break-word;'>9</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

路由类型定义如表98所示。同级路由，指使用与本站点层级相同站点，作为下一跳路由站点；上级路由，指使用比本站点低一个层级的站点，作为下一跳路由站点；代理主路径路由，指使用本站点的代理站点，作为下一跳路由站点；上上级路由，指使用比本站点低两个层级的站点，作为下一条路由站点。

<div style="text-align: center;">表 98 路由类型字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示错误的路由类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>表示同级路由类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>表示上级路由类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>表示代理主路径路由类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>表示上上级路由类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 5 1 3 10 19 发现站点列表位图

表示发现站点列表的位域图，比特位的值为1表示该比特位对应的TEI站点，是可被发现的x，并且本报文中，也携带了对应的发现站点信息x

如0字节的1比特值为1，表示的TEI为1；1字节的0比特值为1，表示的TEI为8。

## 5131020 接收发现列表信息

表示发送发现列表报文的站点，在上个路由周期中，接收到其他站点的发现列表报文的总数，若信标帧中“信标使用标志位”为1，则接收其他站点的信标帧的个数。

其中，接收发现列表数0字段，记录的是发现站点列表位图域中，从0字节开始，第一个有效的TEI站点的值。其他的依次类推。

比如，发现站点列表位图域中，从0字节开始，第一个为1的比特位是1字节的0比特，那么接收发现列表数0字段的值，就是指接收TEI为8的站点的发现报文数量。

接收发现列表信息字段如表99所示。

<div style="text-align: center;">表99 接收发现列表信息字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收发现列表数 0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>接收的发现列表报文数量</td></tr></table>