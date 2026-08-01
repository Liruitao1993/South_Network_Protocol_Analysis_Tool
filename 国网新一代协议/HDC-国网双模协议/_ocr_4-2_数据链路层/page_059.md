<div style="text-align: center;">表95（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线</td><td style='text-align: center; word-wrap: break-word;'>16</td><td style='text-align: center; word-wrap: break-word;'>0 5</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>16</td><td style='text-align: center; word-wrap: break-word;'>6 7</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理站点信道质量</td><td style='text-align: center; word-wrap: break-word;'>17</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理站点通信成功率</td><td style='text-align: center; word-wrap: break-word;'>18</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理站点下行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>19</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点总数</td><td style='text-align: center; word-wrap: break-word;'>20 21</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>16</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>发送发现列表报文个数</td><td style='text-align: center; word-wrap: break-word;'>22</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上行路由条目总数</td><td style='text-align: center; word-wrap: break-word;'>23</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由周期到期剩余时间</td><td style='text-align: center; word-wrap: break-word;'>24 25</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>16</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>位图大小</td><td style='text-align: center; word-wrap: break-word;'>26 27</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>16</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最小通信成功率</td><td style='text-align: center; word-wrap: break-word;'>28</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>29 31</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>24</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上行路由条目信息</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>发现站点列表位图</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收发现列表信息</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513102 TEI

表示发送发现列表报文的站点的终端设备标识TEI。

## 513103 代理 TEI

表示发送发现列表报文的站点的代理站点的TEI。

## 513104 角色

表示发送发现列表报文的站点的角色。

## 513105 层级

表示发送发现列表报文的站点的网络层级。

## 513106 MAC地址

表示发送发现列表报文的站点的MAC地址。

## 513107 CCO MAC 地址

指本网络CCO的MAC地址。

## 513108 相线

表示发送发现列表报文的站点，评估出的本站点的所属相线，按照优先顺序填写。其中第一相线表示是本站点最有可能所属的相线。站点相线信息，需要根据接收的信标帧中的相线信息进行评估。

定义如表96所示。