<div style="text-align: center;">表4（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>组网序列号</td><td style='text-align: center; word-wrap: break-word;'>13</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>14</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>15</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原始源 MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>0 或者 16 21</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>0 或者 48</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原始目的 MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>0 或者 22 27</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>0 或者 48</td></tr></table>

## 51132 版本

版本是一个4比特的字段。该字段用来指示MAC帧头的字段定义版本号。标准MAC帧头中值为0。

## 51133 原始源 TEI

MSDU的原始源终端设备的标识，即最初产生MSDU的源终端设备的TEI。

## 5 1 1 3 4 原始目的 TEI

MSDU的最终目的终端设备的标识，即最终需要处理MSDU的目的终端设备的TEI。

## 51135 发送类型

报文发送的类型，含义如表5所示。

<div style="text-align: center;">表5 发送类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>单播</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>全网广播</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>本地广播</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>代理广播</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51136 发送次数限值

站点对报文最大发送次数。如果该字段值为零，则可以使用本地重发次数。

需要确认回应的报文，如果回应为成功，则不需要继续重发。

不需要确认回应的报文，则报文的总发送次数必须达到发送次数限值。

## 51137 MSDU序列号

指产生MSDU的原始设备分配给该MSDU的递增序列号。

## 51138 MSDU长度

MAC帧中携带的MSDU的长度。