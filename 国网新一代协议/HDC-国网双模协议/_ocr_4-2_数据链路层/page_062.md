<div style="text-align: center;">表99（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收发现列表数 1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>接收的发现列表报文数量</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>接收的发现列表报文数量</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收发现列表数 N</td><td style='text-align: center; word-wrap: break-word;'>N</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>接收的发现列表报文数量</td></tr></table>

## 5 1 3 11 通信成功率上报报文

## 513111 通信成功率上报报文格式

通信成功率上报报文（MMeSuccessRateReport）格式的定义如表100所示。本报文只需要由代理站点发送。

<div style="text-align: center;">表 100 通信成功率上报报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td rowspan="2">TEI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>07</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>03</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>47</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点总数</td><td style='text-align: center; word-wrap: break-word;'>23</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>2 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信成功率信息</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513112 TEI

表示代理站点自身的设备标识TEI。通信成功率报文，由代理站点发送。

## 513113 站点总数

表示代理站点的子站点个数。同时也是通信成功率信息字段中STA表项的数目。

## 513114 通信成功率信息

表示通信成功率信息，包含了代理站点的每个子站点的通信成功率×通信成功率信息字段中，每个STA成功率信息的定义如表101所示×表示子站点的设备标识×下行通信成功率（DownCommRate）表示代理站点到子站点的下行通信成功率×上行通信成功率（UpCommRate）表示子站点到代理站点的上行通信成功率×

<div style="text-align: center;">表101 成功率信息</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td rowspan="2">站点的 TEI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td><td rowspan="2">站点的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>下行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>下行通信成功率</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>上行通信成功率</td></tr></table>