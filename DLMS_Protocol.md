

<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

# DLMS 协议培训



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

## CONTENTS

1. 前言 ..... 1    
2. IEC 62056-21 E 模式通信流程 ..... 1    
3. HDLC 帧格式 ..... 2    
3.1. 标志域 ..... 3    
3.2. 帧格式域 ..... 3    
3.3. 地址域 ..... 3    
3.4. 控制域格式 ..... 5    
3.5. 帧序算法 ..... 7    
3.6. 头校验序列（HCS）域 ..... 9    
3.7. 信息域 ..... 9    
3.8. 帧校验序列（FCS）域 ..... 9    
4. 链路层链接与断开 ..... 9    
4.1. IEC1107 模式 E ..... 9    
4.2. 链路层的链接 ..... 10    
4.3. 链路层的断开 ..... 11    
5. 应用层的链接 ..... 11    
5.1. 编码规则 ..... 11    
5.2. AARQ APDU 和 AARE APDU 规范 ..... 12    
5.3. AARQ-PDU 的编码例子 ..... 12    
5.3.1. NS（无安全认证）的 AARQ 报文 ..... 12    
5.3.2. LLS（低安全级别）的 AARQ 报文 ..... 12    
5.4. AARE-PDU 的编码例子 ..... 12    
6. 应用层的断开释放（RLRQ 与 RLRE） ..... 12    
6.1. 报文示例 ..... 12    
7. 读操作（GET） ..... 13    
7.1. GET. REQUEST ..... 13    
7.1.1. 正常抄读： ..... 13    
7.2. GET. RESPONSE ..... 13    
7.2.1. 正常抄读的应答 ..... 14    
8. 写操作（SET） ..... 14    
8.1. SET. REQUEST ..... 14    
8.1.1. 写正常数据： ..... 14    
8.2. SET. RESPONSE ..... 15



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

9. 方法操作 (ACTION) ..... 15    
9.1. ACTION. REQUEST ..... 15    
9.1.1. 执行正常数据 ..... 16    
9.2. ACTION. RESPONSE ..... 16    
9.2.1. 正常应答 ..... 16    
9.2.2. 非正常应答 ..... 17    
10. 帧类型标志 ..... 18    
11. TCP 的格式 ..... 19    
11.1. TCP 头格式 ..... 19    
11.2. 报文举例 ..... 20    
12. RR 帧的处理 ..... 20    
12.1. PC 发出的数据表未接收, PC 等不到表回应, 发出 RR 帧 ..... 20    
12.2. PC 发出的数据表收到, PC 等不到表的回应, 发出 RR 帧 ..... 21



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

## 1. 前言

本文档适合于初次接触 DLMS 协议的人员, 想要更进一步学习的请查看蓝皮书、绿皮书（本文当中如无特声明，蓝皮书是指:《Blue Book Edition 13.pdf》，绿皮书是指《Green-Book-Ed-10-V1.0.pdf》）。

## 2. IEC 62056-21 E 模式通信流程

DLMS/COSEM 协议中将 Communication_profile 分为 TCP_profile 和 HDLC_profile 两种，而使用 HDLC_profile 的又分为 E 模式和直接 HDLC，两者的唯一的区别是 E 模式有波特率 300bps 转到 Zpbs 的握手过程，而直接 HDLC 直接进入波特率 Z 下通信。下图为电能表在 IEC62056-21 E 模式下正常工作时的通信流程：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//e260aed1-8efa-4695-941c-cc259c1c31f9/markdown_4/imgs/img_in_image_box_121_181_987_1226.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A35%3A58Z%2F-1%2F%2Fc7cfa429f2db2be8083bd86518c2073f14ce35c3ec4eca2d1fcc1b69e7463b51" alt="Image" width="72%" /></div>


整个通信过程为C/S模式，表计充当服务端，HHU/PC为客户端。每一次通信过程由客户端发起，服务端应答。

## 3. HDLC 帧格式

IEC62056-21 E模式中通信链路帧采用HDLC帧格式，除信息域按其指定格式外，其他域均为16进制传送，其格式如下：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>标志</td><td style='text-align: center; word-wrap: break-word;'>帧格式</td><td style='text-align: center; word-wrap: break-word;'>目的地址</td><td style='text-align: center; word-wrap: break-word;'>源地址</td><td style='text-align: center; word-wrap: break-word;'>控制</td><td style='text-align: center; word-wrap: break-word;'>HCS</td><td style='text-align: center; word-wrap: break-word;'>信息</td><td style='text-align: center; word-wrap: break-word;'>FCS</td><td style='text-align: center; word-wrap: break-word;'>标志</td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

### 3.1. 标志域

标志域的长度为一字节，值为7EH。当两个或多个帧连续传输时，这一个标志既要用作前一帧的结束标志，又要用作下一个帧的开始标志，如图11所示。

注：当两个传输的字符之间的时段没有超过指定的最大内部字节周期时，帧可以连续传输。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>7E</td><td style='text-align: center; word-wrap: break-word;'>帧 I</td><td style='text-align: center; word-wrap: break-word;'>7E</td><td style='text-align: center; word-wrap: break-word;'>帧 I+1</td><td style='text-align: center; word-wrap: break-word;'>7E</td><td style='text-align: center; word-wrap: break-word;'>帧 I+2</td><td style='text-align: center; word-wrap: break-word;'>7E</td></tr></table>

### 3.2. 帧格式域

帧格式域的长度为两个字节，它由三个子域组成：Frame_type子域(4 bit)，分段位(S, 1 bit)和帧长度子域(11 bit)，见图12。

MSB



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>S</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>

格式类型子域的值为1010（二进制）。

分段位S表示是否有后续帧，如果服务端给客户端传送的数据能在一帧内传送完，那么S=0，如果有后续帧那么S=1。

长度子域的值是除两个7E标志之外的8位位组数。在一般情况下，帧长度不会超过256，因此帧格式域第一个字节为 A0 或者 A8，第二个字节表示该帧的长度。

### 3.3. 地址域

这个帧有两个地址域：一个目的HDLC地址和一个源HDLC地址。根据数据的传输方向，客户机端地址和服务器地址都可以是目标地址或源地址。

客户机端地址总是用一个字节表示。扩展地址的使用把客户机地址的范围限制在128。

在服务器端，为了能在一个物理设备内寻址一个以上的逻辑装置并且支持多站配置，可以将HDLC地址分为两部分。一部分称为“高端HDLC地址”用于逻辑设备（一个物理设备内可独立寻址的实体）寻址，而第二部分——“低端HDLC地址”将用于物理设备（多站配置的一个物理设备）寻址。高端HDLC地址总是存在，而低端HDLC地址在不需要时可不用。

HDLC地址扩展机制应用于以上两种地址域。这种地址扩展说明可变长度的地址域，但是考虑到该协议，一个完整的HDLC地址域的长度被限制为一字节，两字节或四字节如下：

• 一字节：只有高端HDLC地址存在。

两字节：一字节高端HDLC地址和一字节低端HDLC地址。

四字节：两字节高端HDLC地址和两字节低端HDLC地址。

上述三种情况在下图说明。

一字节地址结构:

LSB



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>高端HDLC 地址</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

两字节地址结构:



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>高端HDLC地址</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>低端HDLC地址</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

第一字节

第二字节

四字节地址结构：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td colspan="2">LSB</td><td colspan="2">LSB</td><td colspan="2">LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>高端HDLC高字节</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>高端HDLC低字节</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>低端HDLC高字节</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>低端HDLC高字节</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>第一字节</td><td colspan="2">第二字节</td><td colspan="2">第三字节</td><td colspan="3">第四字节</td></tr></table>

这种可变长度HDLC地址结构为每字节保留了一位来标示所给字节是最后一字节还是有字节跟随。这意味着一字节地址的地址范围是0…0x7F，两字节地址的地址范围是0…0x3FFF。

单独的，多播及广播的寻址可由高端HDLC地址和低端HDLC地址方便提供。

例如，一个HDLC帧以下列地址从客户机端发送到服务器端：

客户HDLC地址 =  $ 3A_{H} = 00111010_{B} $

服务器HDLC地址（用四字节寻址）

低端HDLC地址 = 3FFF $ _{H} $ = 00111

高端HDLC地址 = 1234 = 0001001000110100

消息地址域应包含以下8位字组：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="5">服务器地址</td><td colspan="2">客户机地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>高端HDLC, 高字节</td><td style='text-align: center; word-wrap: break-word;'>高端HDLC, 低字节</td><td style='text-align: center; word-wrap: break-word;'>低端HDLC, 高字节</td><td style='text-align: center; word-wrap: break-word;'>低端HDLC, 低字节</td><td style='text-align: center; word-wrap: break-word;'>HDLC 地址</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'>LSB</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0 1 0 0 1 0 0</td><td style='text-align: center; word-wrap: break-word;'>0 1 1 0 1 0 0</td><td style='text-align: center; word-wrap: break-word;'>0 1 1 1 1 1 1</td><td style='text-align: center; word-wrap: break-word;'>0 1 1 1 1 1 1</td><td style='text-align: center; word-wrap: break-word;'>1 0 1 1 1 0 1 0 1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>第一字节</td><td style='text-align: center; word-wrap: break-word;'>第二字节</td><td style='text-align: center; word-wrap: break-word;'>第三字节</td><td style='text-align: center; word-wrap: break-word;'>第四字节</td><td style='text-align: center; word-wrap: break-word;'>第五字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td colspan="4">目的地址</td><td style='text-align: center; word-wrap: break-word;'>源地址</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td colspan="4">4868FEFF</td><td style='text-align: center; word-wrap: break-word;'>75</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

<Blue-Book-Ed14--V1.0.pdf>蓝皮书描述地址第216页

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//b5a1d73c-1bc7-4a3e-97df-6ae97347d59e/markdown_1/imgs/img_in_image_box_135_1114_881_1319.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A15Z%2F-1%2F%2Faa745833658fc9fbb00e7c70ce4d4928c77cf694063fcb9bdf0560ad7430afeb" alt="Image" width="62%" /></div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

### 3.4. 控制域格式

命令/应答帧控制字段的编码方式为模式8，如ISO/IEC 13239的5.5及下表规定。

<div style="text-align: center;"><div style="text-align: center;">表7 控制字段格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="8">MSB</td><td colspan="3">LSB</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>I</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>P/F</td><td style='text-align: center; word-wrap: break-word;'>S</td><td style='text-align: center; word-wrap: break-word;'>S</td><td style='text-align: center; word-wrap: break-word;'>S</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>RR</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>P/F</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>RNR</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>R</td><td style='text-align: center; word-wrap: break-word;'>P/F</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>SNRM</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>P</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DISC</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>P</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>UA</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>F</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DM</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>F</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>FRMR</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>F</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>UI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>P/F</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

I Information (a HDLC frame type) 信息帧，有帧序。

RR Receive Ready (a HDLC frame type) 接收准备帧，如果PC端没有收到，可以发此帧，等表的应答。

RNR  Receive Not Ready (a HDLC frame type)  接收未准备。

SNRM Set Normal Response Mode (a HDLC frame type) 建立链路层联接

注：NRM链路，即正常响应方式链路，他具有哪些特点，我摘要如下(来自中兴通讯一份内训资料，权威的需参照国家标准)

常响应方式（NRM）适用于不平衡链路结构(如下图)，即用于点-点和点-多点的链路结构中，特别是点-多点链路。这种方式中，由主站控制整个链路的操作，负责链路的初始化、数据流控制和链路复位等。从站的功能很简单，它只有在收到主站的明确允许后，才能发出响应。从站电表处理被动状态

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//b5a1d73c-1bc7-4a3e-97df-6ae97347d59e/markdown_2/imgs/img_in_image_box_176_1039_1076_1311.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A16Z%2F-1%2F%2F36e00620eff0cc0062e0af32e36c7f248721d1774a66bca3ee1de49270d3f145" alt="Image" width="75%" /></div>


<div style="text-align: center;"><div style="text-align: center;">(a) 不平衡链路结构</div> </div>


DISC Disconnect (a HDLC frame type) 断开链路

UA Unnumbered Acknowledge (a HDLC frame type) 无编号确认的

DM Disconnected Mode (a HDLC frame type) 断开模式

FRMR: Frame Reject (a HDLC frame type) 帧拒绝应答。

UI Unnumbered Information (a HDLC frame type) 未确认信息



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

关于表应答断开链接特别注意：

如果表收到53请求断开. 如果此时表在收此帧之前处于连接状态, 那么应答为73 即UA帧, 当表收到此帧时表认为已经处于断开状态那么应答为DM即1F,

这里RRR是接收序列号N(R)，SSS是发送序列号N(S)，P/F是查询/结束位。

链路层链接好即 SNRM UA 帧后，RRR 和 SSS 均为 000，发送一帧 I 帧 SSS 加 1，接收到一帧 I 帧 RRR 加 1，客户端和服务端都是如此。P/F 标志位中 P 是对客户端而言的，需要响应 P=1，那么广播帧时 P=0；F 是对服务端而言的，F 表示发送是否结束，也就是是不是没有后续帧，F=1 表示有后续帧，因此当客户端收到服务端发送来的帧格式域中 S=1 和此处的 F=1 的帧时，需回应 RR 帧等待接收未接收完的数据。

例如：

//SNRM 帧 100P0011, 因需要响应, P=1, 所以控制字为 93

客户端:7E A0 0A 48 68 FE FF 75 93 D8 F8 7E

//UA 帧 011P0011, 因需要响应, F=1, 所以控制字为 73

服务端:7E A0 21 75 48 68 FE FF 73 7C 16 81 80 12 05 01 80 06 01 80 07 04 00 00 00 01 08 04 00 00 00 01 53 3B

7E

//AARQ帧（属于I类型）RRR=0，SSS=0，P=1，所以控制字为10

//AARQ帧（属于I类型）RRR=0，SSS=0，P=1，所以控制字为10

客户端：7E A0 46 48 68 FE FF 75 10 05 C1 E6 E6 00 60 35 A1 09 06 07 60 85 74 05 08 01 01 8A 02 07 80 8B 07 60 85 74 05 08 02 01 AC 0A 80 08 41 42 43 44 45 46 47 48 BE 10 04 0E 01 00 00 00 06 5F 04 00 00 00 14 00 00 BD BF 7E

//AARE帧（属于I类型）RRR=1，SSS=0，F=1，所以控制字为30

服务端:7E A0 52 75 48 68 FE FF 30 95 39 E6 E7 00 61 41 A1 09 06 07 60 85 74 05 08 01 01 A2 03 02 01 00 A3 05

A1 03 02 01 00 88 02 07 80 89 07 60 85 74 05 08 02 01 AA 0A 80 08 41 42 43 44 45 46 47 48 BE OF 04 OD 08 00 06

5F 04 00 00 00 14 21 34 00 07 14 53 7E

//GET.request（属于I类）RRR=1，SSS=1，P=1，所以控制字为32

客户端:7E A0 1C 48 68 FE FF 75 32 0E 3B E6 E6 00 C0 01 81 00 07 00 00 63 01 00 FF 00 02 DE 82 7E

//GET.response（属于I类）RRR=2，SSS=1，F=0，所以控制字为52；（S=1，所以帧格式为A8）

服务端：7E A8 8C 75 48 68 FE FF 52 CE 26 E6 E7 00 C4 01 81 00 01 22 02 06 02 02 09 0C 07 D3 06 09 FF 09 1D 0D FF FF FF FF 04 06 40 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 0

File name DLMS 协议培训 Date 2022-4-11

Archive N

Version 1.0

10 00 00 10 00 00 02 06 00 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 02 F9 31 7E

//RR 帧 由于上面服务端回的帧中 F=0 S=0 即有后续帧，所以此处客户端应回应 RR 帧等待服务端的后续帧

RRR=2, P=0, 所以控制字为 71

客户端:7E A0 0A 48 68 FE FF 75 71 16 C5 7E

//GET.response 的后续帧 RRR=2, SSS=3, F=0, 所以控制字为 56; (S=1, 所以帧格式为 A8)

服务端:7E A8 8C 75 48 68 FE FF 56 EA 60 06 00 00 00 00 10 00 00 10 00 00 02 06 00 00 00 10 00 00 10 00 00 00 02 06 00 00 00 00 10 00 00 00 02 06 00 00 00 10 00 00 00 00 02 06 00 00 10 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 06 00 00 00 00 02 

### 3.5. 帧序算法

关于帧序的算法,一般我们是参数上述例程,分别在接收和发送端加1来实现,在正常通讯中似乎是没有问题,这主要是表做了兼窗口.同时以前我们没有用到过分段传输的情况.2019年6月康宣采用K公司的软件对T15VD的表进行分段升级,我们才发现以前的帧序的算法不够正确.我们先来看以下的报文监控:



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>序号</td><td style='text-align: center; word-wrap: break-word;'>帧方向</td><td style='text-align: center; word-wrap: break-word;'>帧功能</td><td style='text-align: center; word-wrap: break-word;'>帧序</td><td style='text-align: center; word-wrap: break-word;'>旧算法</td><td style='text-align: center; word-wrap: break-word;'>对方值</td><td style='text-align: center; word-wrap: break-word;'>新算法（接收域为对方的发送域+1, 发送域为对方接收域）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'>SNRM</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'>UA</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'>AARQ</td><td style='text-align: center; word-wrap: break-word;'>10</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'>AARE</td><td style='text-align: center; word-wrap: break-word;'>30</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>表收3, 表发0</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'>ACTION REQUEST</td><td style='text-align: center; word-wrap: break-word;'>32</td><td style='text-align: center; word-wrap: break-word;'>32发送+1</td><td style='text-align: center; word-wrap: break-word;'>PC收3 PC发2</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'>Response</td><td style='text-align: center; word-wrap: break-word;'>52</td><td style='text-align: center; word-wrap: break-word;'>表接收+1,</td><td style='text-align: center; word-wrap: break-word;'>表收5 表发2</td><td style='text-align: center; word-wrap: break-word;'>5=001+001=010；并入PD位0101即为5. 2=0011最低位置1即为2</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'>乱数据帧</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>为1011=B</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>23</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>BA</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>PC收BPC发A</td><td style='text-align: center; word-wrap: break-word;'>B: 1000 100+1=101, 并入PF后即为1011=BA:B-1011最低位置0=A</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>24</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>DA</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>表收D表发A</td><td style='text-align: center; word-wrap: break-word;'>D:A+1 101+1=110, 并入PF后即为1101为DA:B-1最低位置0=A</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>25</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>DC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>PC收DPC发C</td><td style='text-align: center; word-wrap: break-word;'>D:A+1 101+1=110, 并入PF后即为1101为DC:D-1最低位置0=C</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>26</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'>RR</td><td style='text-align: center; word-wrap: break-word;'>F1</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>表收F</td><td style='text-align: center; word-wrap: break-word;'>F:C+1 =1100 110+1=111并入PF后即为F</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>27</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>DE</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>PC收DPC发E</td><td style='text-align: center; word-wrap: break-word;'>D:A+1 101+1=110并入PF后即为1101为DE:F-1最低位置0=E</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>28</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'>RR</td><td style='text-align: center; word-wrap: break-word;'>11</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>表收1</td><td style='text-align: center; word-wrap: break-word;'>1:E+1=111 +1=000, 并入PF后即为0001</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>29</td><td style='text-align: center; word-wrap: break-word;'>PC-&gt;表</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>DO</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>PC收DPC发0</td><td style='text-align: center; word-wrap: break-word;'>D:A+1 101+1=110, 并入PF后即为1101为D0:1-1最低位置0</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>30</td><td style='text-align: center; word-wrap: break-word;'>表-&gt;PC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>3C</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>表收3表发C</td><td style='text-align: center; word-wrap: break-word;'>B:0+1=001并入PF后即为0011为3C:D-1..</td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

### 3.6. 头校验序列（HCS）域

HCS的长度是两个字节。

HCS计算除开始标志和HCS本身外的头的字节数。

HCS的计算方法跟帧校验序列（FCS）类似。不包含信息域的帧，仅含FCS（在这种情况下，HCS被看作FCS）。HCS（和FCS）的计算方法采用CRC校验算法，不等式为 $ X^{***}0+X^{***}5+X^{***}12+X^{***}16 $。

### 3.7. 信息域

信息域可以是任意字节序列。

### 3.8. 帧校验序列（FCS）域

FCS 域的长度是两个字节，用来计算除开始标志和 FCS 本身外的完整的帧长度。不包含信息域的帧只包含 FCS（这里 HCS 被看作 FCS）。

## 4. 链路层链接与断开

### 4.1. IEC1107 模式 E

常用于通过红外口通讯



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

看报文：

Baud Rate :300 , StopBits: 1, Parity: Even, DataBits: 7

发送：/?!

接收：/DZGO\220300HD11FW451 //注意表返回的信息它的通讯波特率要求为 0X30，即 300

/DZG5\220300HD11FW451 //注意表返回的信息它的通讯波特率要求为 0X35, 即 9600

发送切换波特率指令：202

那么切换波特率到 3008, N, 1 以后收到表返回的数据

接收：202

### 4.2. 链路层的链接

链路层的连接包括客户端发送的 SNRM 帧和服务端发送的 UA 帧。

SNRM(Set normal response mode)/UA信息交换不但允许建立连接，而且允许协商一些数据链路参数。该协商的HDLC参数子集包含两部分：

• WINDOW_SIZE 参数（最大窗体数，即一次最多可传输的帧数，这个参数不能大于7）

- MAXIMUM INFORMATION FIELD LENGTH 参数（信息域的最大字节数）

这些参数的缺省值如下:

● 默认WINDOW SIZE=1

● 默认 MAXIMUM INFORMATION FIELD LENGTH=128(80H)

协商规则如下：

协商从SNRM帧开始。该帧可能包含信息域。当信息域存在时，它应采用下面格式(见ISO/IEC132395.5.3.2条):（见绿皮书第137页）

信息域编码的格式举例(参数值为缺省值):



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>81</td><td style='text-align: center; word-wrap: break-word;'>80</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>80</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>80</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>08</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>01</td></tr></table>

这里：

1:

81 $ _{H} $ 格式标识符

80 $ _{H} $ 组标识符

12 $ _{H} $ 组长(18字节)

05 $ _{H} $ 参数标识符(最大信息字段长度，发送)

01 $ _{H} $ 参数长度（1字节）

80 $ _{H} $ 参数值

06 $ _{H} $ 参数标识符(最大信息字段长度，接收)

01 $ _{H} $ 参数长度（1字节）

80 $ _{H} $ 参数值

07 $ _{H} $ 参数标识符(窗口大小, 发送)

04 $ _{H} $ 参数长度（4字节）

00 $ _{H} $ 参数值(值高字节)

00 $ _{H} $ 参数值

00 $ _{H} $ 参数值(值低字节)

08 $ _{H} $ 参数标识符(窗口大小，接收)

04 $ _{H} $ 参数长度

00 $ _{H} $ 参数值(值高字节)



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

 $ 00_{H} $ 参数值

 $ 00_{H} $ 参数值

 $ 01_{H} $ 参数值(值低字节)

具体看报文(不带参数协商的 SNRM 帧)

发送：7E A0 0A 00 02 FE FF 09 93 2E 6F 7E

接收：7E A0 23 09 00 02 FE FF 73 7A 0B 81 80 14 05 02 01 94 06 02 01 74 07 04 00 00 00 01 08

04 00 00 00 01 29 F8 7E

### 4.3. 链路层的断开

断开链路层包括客户端发送的DISC帧和服务端回应的UA/DM帧。

接收到DISC时没有断开链路，服务端回UA，然后链路断开；接收到DISC时链路已经断开则服务端回应DM帧。

DISC帧、UA帧和DM帧固定，只要将地址域及HCS域更换，如下：

DISC帧为 7E A0 0A 48 68 FE FF 75 53 06 C7 7E

UA帧为 7E A0 0A 75 48 68 FE FF 73 29 E5 7E

DM帧为 7E A0 0A 75 48 68 FE FF 1F 98 AD 7E

## 5. 应用层的链接

应用层链接由客户端发起的 AARQ 帧和服务端回应的 AARE 帧构成。主要协商引用机制（逻辑名引用还是短名引用，瑞银暂定为逻辑名引用）、支持的应用操作（读、写、方法）、用户级别等。对于 ASN.1 语义 AARQ、AARE（除用户信息单元中的 Initial 部分）采用的是 BER 编码规则，其余均采用 A-XDR 编码规则。

### 5.1. 编码规则

BER 编码由三部分构成：类型，长度及值，如下图。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Identifier</td><td style='text-align: center; word-wrap: break-word;'>Length</td><td style='text-align: center; word-wrap: break-word;'>Contents</td></tr></table>

那么表达多项内容时则由一系列字节构成，如下：

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//49b9e6e7-03f3-4d2b-831b-4db64a0ee603/markdown_3/imgs/img_in_image_box_222_1114_966_1223.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A40Z%2F-1%2F%2F7bf4a63f381826bb0169242f9b34b1001f5ea184f01f5ff45b36b0fb12a02b31" alt="Image" width="62%" /></div>


A-XDR 编码规则与 BER 编码类似, 只是 A-XDR 编码省略了冗余的类型和长度部分, 比如类型为 integer8 时, 从类型便可看出长度为 1 个字节, 因此可以省略掉长度部分。A-XDR 编码结构如下:

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//49b9e6e7-03f3-4d2b-831b-4db64a0ee603/markdown_3/imgs/img_in_image_box_220_1317_965_1428.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A40Z%2F-1%2F%2F8372ac46a5a0cda7f0867ebfa2520d793ca1eef2ca1e2b6f3aa6cb3ceb6158a0" alt="Image" width="62%" /></div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

### 5.2. AARQ APDU 和 AARE APDU 规范

在COSEM中, AARQ APDU在BER中被编码, 而且包含一个AXDR编码为DLMS-Initiate.request的pdu, 作为用户信息单元内部的 OCTETSTRING。

AARQ和AARE APDU-s规范如下（实际为AARQ AARE帧中信息域的参数，OPTIONAL表示该参数可缺省）

### 5.3. AARQ-pdu 的编码例子

#### 5.3.1. NS（无安全认证）的 AARQ 报文

7EA02E0002FEFF0B10F8E6E6E600601DA109060760857405080101BE10040E01000000065F1F0400001819FFFF3

CTT: 601DA109060760857405080101BE10040E01000000065F1F040060FEDFFFF

#### 5.3.2. LLS(低安全级别) 的 AARQ 报文



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>LLS 发送：7E A0 47 00 02 FE FF 09 10 F4 30 E6 E6 00 60 36 A1 09 06 07 60 85 74 05 08 01 01 8A 02 07 80 8B 07 60 85 74 05 08 02 01 AC 0A 80 08 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32 32</td></tr></table>

## 6. 应用层的断开释放(RLRQ 与 RLRE)

详见绿皮书 P375 页.

### 6.1. 报文示例

RLRQ 的 APDU, 绿皮书 P455 页.

RLRE 的 APDU, 绿皮书 456 页.

WRAPPER[1] Sent 00010010000100056203800100

WRAPPER[1] Rec 00010001001000056303800100



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

## 7. 读操作 (Get)

分为Get. Request和Get. Response。

### 7.1. Get. Request

#### 7.1.1. 正常抄读：

数据请求帧

7E A0 1C 00 02 FE FF 09 54 99 30 E6 E6 00 C0 01 C1 00 01 00 00 60 01 01 FF 02 00 32 BC 71
CO: Get request. 命令

01: requestType 请求的类别 01 表示 Normal Get, 有以下三种类型
Get-Request ::= CHOICE
{
    get-request-normal [1] IMPLICIT Get-Request-Normal,
    get-request-next [2] IMPLICIT Get-Request-Next,
    get-request-with-list [3] IMPLICIT Get-Request-With-List
}

/// <summary>
    /// Normal Get.
    /// </summary>
    Normal = 1,
    /// <summary>
    /// Next data block.
    /// </summary>
    NextDataBlock = 2,
    /// <summary>
    /// Get request with list.
    /// </summary>
    WithList = 3
}

### 7.2. Get. Response

数据响应帧。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

#### 7.2.1. 正常抄读的应答

Get-Response ::= CHOICE
{
    get-response-normal
    get-response-with-datablock
    get-response-with-list
}

Get-Response-Normal ::= SEQUENCE
{
    invoke-id-and-priority
    result
}

Get-Data-Result ::= CHOICE
{
    data
    data-access-result
}

Gurux DLMS Translator

Pdu To XML XML To Pdu

Messages Pdu Data to XML Ciphering

C401C101FA

<GetResponse>
    <GetResponseNormal>
        <!— Priority: High, ServiceClass: Confirmed, ID: 1 —>
        <InvokeIdAndPriority Value="C1" />
    <Result>
        <DataAccessError Value="OtherReason" />
    </Result>
</GetResponseNormal>
</GetResponse>

7E A0 1D 09 00 02 FE FF 74 AE 2F E6 E7 00 C4 01 C1 00 0A 08 45 33 30 30 35 2D 53 41

^00 02 FE FF 52 F5 22 E6 E7 00 C4 01 C2 01 FA 59 07 7E

错误应答：7E A0 14 OB 00 02 FE FF 52 F5 22 E6 E7 00 C4 01 C2 01 FA 59 07 7E

## 8. 写操作(Set)

分为 Set. Request 和 Set. Response。

8.1. Set. Request

#### 8.1.1. 写正常数据：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

30 30 35 2D 53 41 A6 E5 7E (0-0:96.1.1*255 Meter model E3005-SA)

C1 表明文写操作——对应表的应答则为 C5

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//5b69e7c9-401b-4410-83b1-fd227651ad08/markdown_2/imgs/img_in_image_box_490_209_515_238.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A13Z%2F-1%2F%2Fdf6cf6607592da168bb443e61204ee384eef505246257c4f32c2808000926cb2" alt="Image" width="2%" /></div>


01: 表写操作的类型:
01 表示: Writing the value of a single attribute without block transfer
04 表示: Writing the value of a list of attributes without block transfer
C1: InvokeIdAndPriority
00 01 00 00 60 01 01 FF 02: Cosem-Attribute-Descriptor,
00: Selective-Access-Descriptor OPTIONAL. 为 0. 即不带 Selective-Access-Descripto, 特别强调这
这个字节不是用来区分是方法还是写数据的标志.

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//5b69e7c9-401b-4410-83b1-fd227651ad08/markdown_2/imgs/img_in_image_box_112_332_137_361.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A13Z%2F-1%2F%2Fc87605c281800fd3591eb19d491d30b48865732b9fb4bb2a5ee32383d5cf2855" alt="Image" width="2%" /></div>


### 8.2. Set. Response

数据设置响应。
Set-Response ::= CHOICE
{
    set-response-normal [1] IMPLICIT Set-Response-Normal,
    set-response-datablock [2] IMPLICIT Set-Response-Datablock,
    set-response-last-datablock [3] IMPLICIT Set-Response-Last-Datablock,
    set-response-last-datablock-with-list [4] IMPLICIT Set-Response-Last-Datablock-With-List,
    set-response-with-list [5] IMPLICIT Set-Response-With-List
}
正常数据应答：
E A0 14 09 00 02 FE FF 52 A3 2A E6 E7 00 C5 01 C1 01 0D 49 60 7E (0-0:96.1.1*255 Meter
odel E3005-SA 没有写成功返回一个错误)

## 9. 方法操作(Action)

分为 ACTION Request 和 ACTION. Response。

### 9.1. ACTION. Request

请求的格式绿皮书的定义为：

Action-Request ::= CHOICE
{
    action-request-normal [1] IMPLICIT Action-Request-Normal,
    action-request-next-pblock [2] IMPLICIT Action-Request-Next-Pblock,
    action-request-with-list [3] IMPLICIT Action-Request-With-List,
    action-request-with-first-pblock [4] IMPLICIT Action-Request-With-First-Pblock,
    action-request-with-list-and-first-pblock [5] IMPLICIT Action-Request-With-List-And-First-Pblock,
    action-request-with-pblock [6] IMPLICIT Action-Request-With-Pblock
}
以 Action-Request-Normal 为例介绍结构：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

Action-Request-Normal ::= SEQUENCE
{
    invoke-id-and-priority Invoke-Id-And-Priority,
    cosem-method-descriptor Cosem-Method-Descriptor,
    method-invocation-parameters Data OPTIONAL//需要特别注意此参数是可选的. 无数据时为 00, 有数据时先填 01 后需再跟数据.
}

#### 9.1.1. 执行正常数据

action-request-normal[1]

_ou-request-normal[1]
发送:7E A0 1F 00 02 FE FF 09 32 C7 9E E6 E6 00 C3 01 C1 00 09 00 00 0A 00 01 FF 01 01 12 00 01 DF A2 7E(S16VEVF 表需量与 EOB 复位注意组帧方法与写的区别,属性 ID 与方法 ID 的位置)
特别注意红体字 01 不是执行方法的标志位. 而是指方法有引用的参数, 当为 00 时表没有引用的参数.

### 9.2. ACTION. Response

应答格式如下:

Action-Response ::= CHOICE
{
    action-response-normal [1] IMPLICIT Action-Response-Normal,
    action-response-with-pblock [2] IMPLICIT Action-Response-With-Pblock,
    action-response-with-list [3] IMPLICIT Action-Response-With-List,
    action-response-next-pblock [4] IMPLICIT Action-Response-Next-Pblock
}

#### 9.2.1. 正常应答

action-response-normal [1]
应答：7E A0 14 09 00 02 FE FF 52 A3 2A E6 E7 00 C7 01 C1 00 00 FC B4 7E(注意判断是否成功.)



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

</xsd:complexType>

<xsd:complexType name="Action-Response-With-Optional-Data">
    <xsd:sequence>
        <xsd:element name="result" type="Action-Result"/>
        <xsd:element name="return-parameters" minOccurs="8" type="Get-Data-Result"/>
    </xsd:sequence>
</xsd:complexType>

DLMS User Association 2017-06-30 DLMS UA 1000-2 Ed. 8.3 347/511

© Copyright 1997-2017 DLMS User Association

DLMS User Association, DLMS/COSEM Architecture and Protocols, Edition 8.3

<xsd:complexType name="Action-Response-Normal">
    <xsd:sequence>
        <xsd:element name="invoke-id-and-priority" type="Invoke-Id-And-Priority"/>
        <xsd:element name="single-response" type="Action-Response-With-Optional-Data"/>
    </xsd:sequence>
</xsd:complexType>

<xsd:complexType name="Action-Response-With-Pblock">
    <xsd:sequence>
        <xsd:element name="invoke-id-and-priority" type="Invoke-Id-And-Priority"/>
        <xsd:element name="pblock" type="DataBlock-SA"/>
    </xsd:sequence>

如下图的报文分析：

BAUD_RATE
Baud Rate: 9600
LINE_CONTROL StopBits: 1, Parity: No, DataBits: 8
BAUD_RATE
Baud Rate: 9600
LINE_CONTROL StopBits: 1, Parity: No, DataBits: 8
Length: 0010, Data: 7E A0 08 02 FF 61 93 77 08 7E
Length: 0035, Data: 7E A0 21 61 02 FF 73 A3 92 81 80 14 05 02 02 00 06 02 02 00 07 04 00 00 00 01 08 04 00 00 00 01 6F EF 7E
Length: 0071, Data: 7E A0 45 02 FF 61 10 82 03 66 06 00 60 36 A1 09 06 07 60 85 74 05 08 01 01 8A 02 07 80 88 07 60 85 74 05 08 02 01 AC 0A ...
Length: 0008, Data: 7E A0 38 61 02 FF 30 18
Length: 0024, Data: 07 E6 E7 00 61 29 A1 09 06 07 60 85 74 05 08 01 01 A2 03 02 01 00 A3 05
Length: 0026, Data: A1 03 02 01 00 BE 10 04 0E 08 00 06 5F 1F 04 00 00 18 19 02 00 00 07 90 D8 7E
Length: 0031, Data: 7E A0 1D 02 FF 61 32 E0 2E E6 E6 00 C3 01 C1 00 08 00 00 01 00 00 FF 06 01 10 00 05 D2 D2 7E
Length: 0008, Data: 7E A0 12 61 02 FF 52 35
Length: 0012, Data: 68 E6 E7 00 C7 01 C1 00 D0 FC B4 7E
Length: 0010, Data: 7E A0 08 02 FF 61 33 78 CE 7E
Length: 0008, Data: 7E A0 08 61 02 FF 35 56
Length: 0002, Data: A3 7E
Port Closed
引用与优先级
结果
Length: 0031, Data: 7E A0 1D 02 FF 2B 98 A6 9F E6 E6 00 C3 01 81 00 09 00 00 0A 00 00 FF 01 01 12 00 01 65 7E 7E
Length: 0011, Data: 7E A0 12 2B 02 FF B8 78 E9 F6 E7
结果为不成功，返回参数为 0
Length: 0009, Data: 00 C7 01 81 FA 00 F2 33 7E

#### 9.2.2. 非正常应答

如下报文：7EA0150B0002FEFF5220BDE6E700C701C10C010054717E

--Action-Response-With-Optional-Data
OC Action-Result type-unmatched (12),
----return-parameters
01 Data-Access-Result



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

00 success

54717E

type-unmatched (12),
scope-of-access-violated

Action-Response-With-Optional-Data ::= SEQUENCE
{
result     Action-Result,
return-parameters     Get-Data-Result OPTIONAL
}

Get-Data-Result ::= CHOICE
{
data [0] Data,
data-access-result [1] IMPLICIT Data-Access-Result
}

## 10. 帧类型标志

如何查找这个帧类型(命令)字节,那么如果是 PC 端发出的只需要检查 E6 E600 后面的一个字节即可,如果是表应答那么只需要检查 E6 E700 后面的一个字节即可.



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>命令说明</td><td style='text-align: center; word-wrap: break-word;'>HEX 码</td><td style='text-align: center; word-wrap: break-word;'>绿皮书第 P316 页</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Glo get request.加密抄读请求</td><td style='text-align: center; word-wrap: break-word;'>0xC8</td><td style='text-align: center; word-wrap: break-word;'>with global ciphering</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Glo get response.加密抄读应答</td><td style='text-align: center; word-wrap: break-word;'>0xCC</td><td style='text-align: center; word-wrap: break-word;'>绿皮书第 8-3 版第 215 页有 Table 40 - Example:glo-get-request xDLMS APDU 引用 C8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Glo set request.加密写请求</td><td style='text-align: center; word-wrap: break-word;'>0xC9</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Glo set response.加密写应答</td><td style='text-align: center; word-wrap: break-word;'>0xCD</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Glo method request.加密执行方法请求</td><td style='text-align: center; word-wrap: break-word;'>0xFCB</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Glo method response.加密执行方法的应答</td><td style='text-align: center; word-wrap: break-word;'>0xFCF</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Get request.抄读请求</td><td style='text-align: center; word-wrap: break-word;'>0xC0</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Get response.抄读应答</td><td style='text-align: center; word-wrap: break-word;'>0xC4</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Set request.写请求</td><td style='text-align: center; word-wrap: break-word;'>0xC1</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Set response.写应答</td><td style='text-align: center; word-wrap: break-word;'>0xC5</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Action request.执行方法请求</td><td style='text-align: center; word-wrap: break-word;'>0xC3</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Action response.执行方法的应答</td><td style='text-align: center; word-wrap: break-word;'>0xC7</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>AARQ request.</td><td style='text-align: center; word-wrap: break-word;'>0x60</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>AARE request.</td><td style='text-align: center; word-wrap: break-word;'>0x61</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Disconnect request for HDLC framing.断开链路请求</td><td style='text-align: center; word-wrap: break-word;'>0x53</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ded-get-request</td><td style='text-align: center; word-wrap: break-word;'>0XD0</td><td style='text-align: center; word-wrap: break-word;'>with dedicated ciphering</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ded-set-request</td><td style='text-align: center; word-wrap: break-word;'>0XD1</td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>ded-event-notification-request</td><td style='text-align: center; word-wrap: break-word;'>0XD2</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ded-action-Request</td><td style='text-align: center; word-wrap: break-word;'>0XD3</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ded-get-response</td><td style='text-align: center; word-wrap: break-word;'>0XD4</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ded-set-response</td><td style='text-align: center; word-wrap: break-word;'>0XD5</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ded-action-response</td><td style='text-align: center; word-wrap: break-word;'>0XD7</td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

## 11. TCP 的格式

概述

TCP 格式是将 DLMS 的 APDU 加上 TCP 格式的头部组成。

##### 7.3.3.2 The wrapper protocol data unit (WPDU)

The WPDU consists of two parts:

• the wrapper header part, containing the wrapper control information; and

- the data part, containing the DATA parameter – an xDLMS APDU – of the corresponding UDP-DATA.xxx service invocation.

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//2d149844-fe69-472a-b4d6-21fc99ccb5a7/markdown_1/imgs/img_in_image_box_228_678_897_972.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-14T01%3A36%3A45Z%2F-1%2F%2F1fcaf23f94a15ee394b4ef8fb5fff54bccd0619e7be5ff2e109dc7abb3440342" alt="Image" width="56%" /></div>


<div style="text-align: center;"><div style="text-align: center;">NOTE The maximum length of the APDU should be eight bytes less than the maximum length of the UDP datagram.</div> </div>


<div style="text-align: center;"><div style="text-align: center;">Figure 29 – The wrapper protocol data unit (WPDU)</div> </div>


### 11.1. TCP 头格式

由 8 字节组成，依次如下：

版本：固定为1，U16类型

源地址：U16 类型，如果是客户端发出的则填 CLIENT 地址，如果是服务端发则填服务端地址。

目的地址：U16 类型，如果是客户端发出的则填服务端地址，如果是服务端发则填 CLIENT 地址。

数据长度：U16 类型，即要发送的 APDU 的长度。

有关地址取值见图：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>

##### 7.3.3.4 Reserved wrapper port numbers (wPort)

Reserved wPort Numbers are specified in Table 2:

<div style="text-align: center;"><div style="text-align: center;">Table 2 – Reserved wrapper port numbers in the UDP-based DLMS/COSEM TL</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="2">Client side reserved addresses</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Wrapper Port Number</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>No-station</td><td style='text-align: center; word-wrap: break-word;'>0x0000</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Client Management Process</td><td style='text-align: center; word-wrap: break-word;'>0x0001</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Public Client</td><td style='text-align: center; word-wrap: break-word;'>0x0010</td></tr><tr><td rowspan="3">Open for client SAP assignment</td><td style='text-align: center; word-wrap: break-word;'>0x02 ...0x0F
0x11...0xFF</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Server side reserved addresses</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Wrapper Port Number</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>No-station</td><td style='text-align: center; word-wrap: break-word;'>0x0000</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Management Logical Device</td><td style='text-align: center; word-wrap: break-word;'>0x0001</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Reserved</td><td style='text-align: center; word-wrap: break-word;'>0x0002...0x000F</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Open for server SAP assignment</td><td style='text-align: center; word-wrap: break-word;'>0x0010...0x007E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>All-station (Broadcast)</td><td style='text-align: center; word-wrap: break-word;'>0x007F</td></tr></table>

### 11.2. 报文举例

PC 通过 TCP 格式发出的 AARQ:

00010004000000386036a1090607608574050801018a0207808b0760857405080201ac0a80083232323232323232be10040e0100000065f1f0400001819ffff

AMI 系统通过 TCP 格式发出的 AARQ:

00010011000100386036a1090607608574050801018a0207808b0760857405080201ac0a80083232323232323232be10040e0100000065f1f04000018190194

## 12. RR 帧的处理

以下示例以 Q8 表截图.

### 12.1. PC 发出的数据表未接收, PC 等不到表回应, 发出 RR 帧



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>File name</td><td style='text-align: center; word-wrap: break-word;'>DLMS 协议培训</td><td style='text-align: center; word-wrap: break-word;'>Date</td><td style='text-align: center; word-wrap: break-word;'>2022-4-11</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Archive No.</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>Version</td><td style='text-align: center; word-wrap: break-word;'>1.0</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>1115</td><td style='text-align: center; word-wrap: break-word;'>[00000402]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0028, Data: 0F 02 12 00 00 F0 51 FE</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1116</td><td style='text-align: center; word-wrap: break-word;'>[00000470]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_WRITE</td><td style='text-align: center; word-wrap: break-word;'>Length: 0028, Data: 7E A0 1A 02 FF 27 DC FA 02 E6 E6 00 C01 C1 00 07 01 00 02 01 01 FF 03 00 1C 88 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1117</td><td style='text-align: center; word-wrap: break-word;'>[00000480]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0001, Data: 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1118</td><td style='text-align: center; word-wrap: break-word;'>[00000481]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0018, Data: A1 29 27 02 FF FC 7A ED E6 E7 00 C4 02 C1 00 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1119</td><td style='text-align: center; word-wrap: break-word;'>[00000482]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0018, Data: 01 00 82 01 10 01 3C 02 04 12 00 04 09 06 01 00 0F 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1120</td><td style='text-align: center; word-wrap: break-word;'>[00000483]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0017, Data: 00 FF 0F 02 12 00 00 02 04 12 00 04 09 06 01 00 0F</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1121</td><td style='text-align: center; word-wrap: break-word;'>[00000484]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0015, Data: 06 00 FF 0F 05 12 00 00 02 04 12 00 04 09 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1122</td><td style='text-align: center; word-wrap: break-word;'>[00000485]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 01 00 0F 06 01 FF 0F 02 12 00 00 02 04 12 00 04</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1123</td><td style='text-align: center; word-wrap: break-word;'>[00000487]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 09 06 01 00 0F 06 01 FF 0F 05 12 00 00 02 04 12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1124</td><td style='text-align: center; word-wrap: break-word;'>[00000488]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 00 04 09 06 01 00 0F 06 02 FF 0F 02 12 00 00 02</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1125</td><td style='text-align: center; word-wrap: break-word;'>[00000489]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0017, Data: 04 12 00 04 09 06 01 00 0F 06 02 FF 0F 05 12 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1126</td><td style='text-align: center; word-wrap: break-word;'>[00000490]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 02 04 12 00 04 09 06 01 00 0F 06 03 FF 0F 02 12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1127</td><td style='text-align: center; word-wrap: break-word;'>[00000491]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0015, Data: 00 00 02 04 12 00 04 09 06 01 00 0F 06 03 FF</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1128</td><td style='text-align: center; word-wrap: break-word;'>[00000492]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 0F 05 12 00 00 02 04 12 00 04 09 06 01 00 0F 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1129</td><td style='text-align: center; word-wrap: break-word;'>[00000493]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 04 FF 0F 02 12 00 00 02 04 12 00 04 09 06 01 00 0F 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1130</td><td style='text-align: center; word-wrap: break-word;'>[00000494]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0015, Data: 0F 06 04 FF 0F 05 12 00 00 02 04 12 00 04 09 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1131</td><td style='text-align: center; word-wrap: break-word;'>[00000495]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 06 00 FF 0F 05 12 00 00 02 04 12 00 00 02 04 12 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1132</td><td style='text-align: center; word-wrap: break-word;'>[00000496]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 04 09 06 01 00 0F 05 12 00 00 02 04 12 00 00 02 04 12 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1133</td><td style='text-align: center; word-wrap: break-word;'>[00000497]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 12 00 04 09 06 01 00 0F 05 12 00 00 02 04 12 00 00 02 04 12 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1134</td><td style='text-align: center; word-wrap: break-word;'>[00000498]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 02 04 12 00 04 09 06 01 00 0F 05 12 00 00 02 04 12 00 00 02 04 12 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1135</td><td style='text-align: center; word-wrap: break-word;'>[00000499]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016, Data: 00 00 02 04 12 00 04 09 06 01 00 0F 05 12 00 00 02 04 12 00 00 02 04 12 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1136</td><td style='text-align: center; word-wrap: break-word;'>[00000500]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0007, Data: 02 12 00 00 58 98 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1137</td><td style='text-align: center; word-wrap: break-word;'>[00000508]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_WRITE</td><td style='text-align: center; word-wrap: break-word;'>Length: 0022, Data: 7E A0 14 02 FF 27 FE 52 61 E6 E6 00 C02 C1 00 00 00 01 51 BE 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1138</td><td style='text-align: center; word-wrap: break-word;'>[00003631]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_WRITE</td><td style='text-align: center; word-wrap: break-word;'>Length: 0010, Data: 7E A0 08 27 02 FF 27 F1 05 54 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1139</td><td style='text-align: center; word-wrap: break-word;'>[00003642]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0010, Data: 7E A0 08 27 02 FF 27 F1 61 59 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1140</td><td style='text-align: center; word-wrap: break-word;'>[00006647]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_WRITE</td><td style='text-align: center; word-wrap: break-word;'>Length: 0022, Data: 7E A0 14 02 FF 27 FE 52 61 E6 E6 00 C02 C1 00 00 00 01 51 BE 7E</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1141</td><td style='text-align: center; word-wrap: break-word;'>[00006658]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0003, Data: 7E A1 27</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1142</td><td style='text-align: center; word-wrap: break-word;'>[00006660]</td><td style='text-align: center; word-wrap: break-word;'>IRP_MI_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0034, Data: 27 02 FF 1E DE 48 E6 E7 00 C4 02 C1 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00</td></tr></table>

### 12.2. PC 发出的数据表收到, PC 等不到表的回应, 发出 RR 帧



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>2228</td><td style='text-align: center; word-wrap: break-word;'>[00000593]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0005. Data: 00 00 8A A7 7E</td><td style='text-align: center; word-wrap: break-word;'>发送完成后,新</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2229</td><td style='text-align: center; word-wrap: break-word;'>[00000659]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_WRITE</td><td style='text-align: center; word-wrap: break-word;'>Length: 0047. Data: 7E A0 2D 02 2F 27 54 B7 EE E6 E6 00 C0 01 C1 00 07 01 00 05 02 01 02 02 04 06 00 00 00 01 06 00 00 00 0C 12 00</td><td style='text-align: center; word-wrap: break-word;'>开通讯</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2230</td><td style='text-align: center; word-wrap: break-word;'>[00000672]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0001. Data: 7E</td><td rowspan="15">PC未收到表返回的数据</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2231</td><td style='text-align: center; word-wrap: break-word;'>[00000674]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0020. Data: A0 FD 27 02 FF 74 36 33 E6 E7 00 C4 02 C1 00 00 00 00 01 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2232</td><td style='text-align: center; word-wrap: break-word;'>[00000675]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: 81 E5 01 04 02 2D 06 00 05 1 CE F0 06 00 05 1 CE F</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2233</td><td style='text-align: center; word-wrap: break-word;'>[00000676]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0017. Data: 06 00 00 00 00 06 00 00 00 06 00 00 00 06 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2234</td><td style='text-align: center; word-wrap: break-word;'>[00000677]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0017. Data: 05 1 CE F0 06 00 05 1 CE F0 06 00 00 00 06 00 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2235</td><td style='text-align: center; word-wrap: break-word;'>[00000678]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: 00 06 00 00 00 06 00 00 00 06 00 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2236</td><td style='text-align: center; word-wrap: break-word;'>[00000679]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0015. Data: 06 00 00 00 00 06 00 00 00 06 00 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2237</td><td style='text-align: center; word-wrap: break-word;'>[00000680]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: 06 00 00 00 02 06 00 00 02 06 00 00 00 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2238</td><td style='text-align: center; word-wrap: break-word;'>[00000681]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0017. Data: 00 00 00 00 06 00 00 00 06 00 00 02 06 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2239</td><td style='text-align: center; word-wrap: break-word;'>[00000682]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0015. Data: 00 02 06 00 00 00 06 00 00 00 00 06 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2240</td><td style='text-align: center; word-wrap: break-word;'>[00000683]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: 00 00 06 00 00 00 06 00 00 00 00 06 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2241</td><td style='text-align: center; word-wrap: break-word;'>[00000684]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0015. Data: 00 06 00 00 00 06 00 00 00 06 00 05 1C</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2242</td><td style='text-align: center; word-wrap: break-word;'>[00000685]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: EF 06 00 05 1 CE F0 06 00 00 00 00 00 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2243</td><td style='text-align: center; word-wrap: break-word;'>[00000687]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: D6 00 00 00 00 06 00 05 1 CE F0 06 00 05 1 CE F0 06</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2244</td><td style='text-align: center; word-wrap: break-word;'>[00000688]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0017. Data: 00 00 00 00 06 00 00 00 06 00 00 00 00 00 00 00 00 00 00</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2245</td><td style='text-align: center; word-wrap: break-word;'>[00000689]</td><td style='text-align: center; word-wrap: break-word;'>IRP_ML_READ</td><td style='text-align: center; word-wrap: break-word;'>Length: 0016. Data: D0 00 06 00 00 00 00 06 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00</td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

