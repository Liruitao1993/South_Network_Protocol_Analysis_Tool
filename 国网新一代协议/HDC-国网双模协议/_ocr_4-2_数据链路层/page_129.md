通过MSDU发送原语，应用层可以将APDU等MSDU帧形式的数据，交由数据链路层进行发送。MSDU发送原语的语义如表158所示。

<div style="text-align: center;">表 158 MSDU 发送原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU</td><td style='text-align: center; word-wrap: break-word;'>字节流</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>组成MSDU的字节流</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU长度</td><td style='text-align: center; word-wrap: break-word;'>整型</td><td style='text-align: center; word-wrap: break-word;'>2 2012</td><td style='text-align: center; word-wrap: break-word;'>MSDU的长度、总字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原始目的地址</td><td style='text-align: center; word-wrap: break-word;'>6字节 MAC地址</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>MSDU帧的最终接收站点的MAC地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原始源地址</td><td style='text-align: center; word-wrap: break-word;'>6字节 MAC地址</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>MSDU帧的初始创建站点的MAC地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU类型</td><td style='text-align: center; word-wrap: break-word;'>1字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>表示业务报文类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>链路标识符（LID）</td><td style='text-align: center; word-wrap: break-word;'>1字节</td><td style='text-align: center; word-wrap: break-word;'>0 254</td><td style='text-align: center; word-wrap: break-word;'>0 3。表示优先级；\n4 254。表示业务分类；\n255。表示无效值</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>链路类型</td><td style='text-align: center; word-wrap: break-word;'>1字节</td><td style='text-align: center; word-wrap: break-word;'>0 2</td><td style='text-align: center; word-wrap: break-word;'>0。表示自动选择链路；\n1。电力线载波链路；\n2。无线链路</td></tr></table>

## 54222 数据链路层处理

数据链路层将MSDU报文封装为MAC帧。

数据链路层发送MSDU报文时，根据发送原语中的原始目的地址，原始源地址，MSDU类型等，生成MAC帧头。

数据链路层对MSDU报文内容不做修改。

数据链路层根据链路标识符，对报文进行调度发送，当链路标识符为无效值时，按照缺省优先级调度发送。

数据链路层根据链路类型选择在电力线载波还是无线空口上发送，当链路类型为无效值时，数据链路层自动选择链路进行发送。

## 5423 MSDU接收原语

## 54231 原语定义

数据链路层通过MSDU接收原语，通知应用层接收MSDU报文。MSDU接收原语的语义如表159所示。

<div style="text-align: center;">表 159 MSDU 接收原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU</td><td style='text-align: center; word-wrap: break-word;'>字节流</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>组成MSDU的字节流</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU长度</td><td style='text-align: center; word-wrap: break-word;'>整型</td><td style='text-align: center; word-wrap: break-word;'>2 2012</td><td style='text-align: center; word-wrap: break-word;'>MSDU的长度、总字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原始目的地址</td><td style='text-align: center; word-wrap: break-word;'>6字节MAC地址</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>MSDU报文的最终接收站点的MAC地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原始源地址</td><td style='text-align: center; word-wrap: break-word;'>6字节MAC地址</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>MSDU报文的初始创建站点的MAC地址</td></tr></table>