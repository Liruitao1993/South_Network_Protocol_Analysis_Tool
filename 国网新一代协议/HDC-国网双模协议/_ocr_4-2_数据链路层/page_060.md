<div style="text-align: center;">表 96 相线评估信息字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>比特位号</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 1</td><td style='text-align: center; word-wrap: break-word;'>0 1</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>评估出的第一相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 2</td><td style='text-align: center; word-wrap: break-word;'>2 3</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>评估出的第二相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 3</td><td style='text-align: center; word-wrap: break-word;'>4 5</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>评估出的第三相线</td></tr></table>

## 513109 代理站点信道质量

表示发送发现列表报文的站点，评估出的接收其代理站点报文时的信道质量。信道质量用原始信噪比数据表示。

## 5 1 3 10 10 代理站点通信成功率

表示发送发现列表报文的站点，与其代理站点之间的上下行通信成功率。

使用百分比数据表示，如与代理站点的通信成功率为78%，则该值填写为78。

## 5 1 3 10 11 代理站点下行通信成功率

表示发送发现列表报文的站点，接收其代理站点的下行报文的成功率。

## 5131012 站点总数

表示发送发现列表报文的站点，在发现列表报文中，携带了发现站点信息的站点数量。

## 5 1 3 10 13 发送发现列表报文个数

表示发送发现列表报文的站点在上个路由周期内发送的发现列表报文的总数，若信标帧中“信标使用标志位”为1，发送发现列表报文个数包含站点在上个路由周期内发送的信标帧的个数。

## 5 1 3 10 14 上行路由条目总数

表示发送发现列表报文的站点到达CCO的上行路由表项数目，最大支持5条路由表项。

## 5131015 路由周期到期剩余时间

表示发送发现列表报文的站点，计算出的距离当前路由周期到期的剩余时间，单位：秒。

## 5131016 最小通信成功率

表示发送发现列表报文的站点到CCO的整个路径中，某级最弱连接的通信成功率x

## 5131017 位图大小

表示“发现站点列表位图”字段的大小，单位是字节。

## 5 1 3 10 18 上行路由条目信息

表示发送发现列表的站点，到达CCO的上行路由表项信息。表项的长度是2字节。上行路由条目总数，定义如表97所示。