<div style="text-align: center;">表11（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>消息类型</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td rowspan="2">MSDU 长度</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">11</td></tr><tr><td rowspan="2">3</td><td style='text-align: center; word-wrap: break-word;'>0 2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>3 7</td><td style='text-align: center; word-wrap: break-word;'>5</td></tr></table>

## 51142 版本

版本是一个4比特的字段。该字段用来指示MAC帧头的字段定义版本号。单跳MAC帧头中值为1。

## 51143 消息类型

承载MSDU报文消息的类型，含义如表12所示。

<div style="text-align: center;">表12 消息类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>发现列表消息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1 127</td><td style='text-align: center; word-wrap: break-word;'>保留（用于管理消息类型扩展）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>128</td><td style='text-align: center; word-wrap: break-word;'>应用层报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>129</td><td style='text-align: center; word-wrap: break-word;'>IPV4 报文</td></tr></table>

## 51144 MSDU长度

MAC帧中携带的MSDU的长度。

## 5115 MSDU

MAC层业务数据单元，可以是需要传送的应用层业务数据，也可以是MAC层的管理消息。

## 5116 完整性校验

完整性校验是针对MAC帧计算的循环冗余校验值。计算完整性校验值时，不包括MAC帧头。完整性校验使用的是32比特的循环冗余校验算法。

## 512 MPDU 帧格式

## 5121 MPDU 帧格式定义

MPDU是MAC层协议数据单元，由MAC子层提供给物理层，在不同站点的物理层之间传送数据的基本传输单元。载波信道上带有多个物理块载荷的MPDU称为长MPDU，带有一个或者不携带物理块载荷称为短MPDU。载波MPDU帧格式如图3所示。