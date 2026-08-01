<div style="text-align: center;">表67（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x2</td><td style='text-align: center; word-wrap: break-word;'>看门狗复位</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x3</td><td style='text-align: center; word-wrap: break-word;'>程序指针异常</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

Boot版本号用于定义Boot的版本号。

软件版本号，是一个2字节字段，使用BCD码表示，与本地通信模块接口协议保持一致。版本时间，是一个2字节字段，使用BIN码表示。年月日的具体表示方法，如表68所示。

<div style="text-align: center;">表 68 版本时间字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>年</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>7</td></tr><tr><td rowspan="2">月</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>7</td><td rowspan="2">4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>02</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>日</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>37</td><td style='text-align: center; word-wrap: break-word;'>5</td></tr></table>

厂商代码，是一个2字节字段，使用ASCII码表示，与本地通信模块接口协议保持一致。

## 513212 硬复位累积次数

记录设备的硬件复位的累计次数。

## 513213 软复位累积次数

记录设备的软件复位的累计次数。

## 513214 代理类型

表示代理站点的类型，定义如表69所示。

<div style="text-align: center;">表69 代理类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示是站点动态选择的代理。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留。</td></tr></table>

## 513215 端到端序列号

表示端到端的管理消息序列号。请求入网的站点，在产生关联请求报文时，需要获取一个序列号，CCO在确认关联入网时，需要在确认报文中携带关联请求报文中的端到端管理报文序列号。

## 513216 管理 ID 信息

管理ID信息为24字节的标识符，用于对双模通信芯片的唯一性标识。

## 5133 关联确认报文