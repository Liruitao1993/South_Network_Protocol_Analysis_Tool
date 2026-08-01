## 54232 数据链路层处理

数据链路层在接收到的MAC帧后，对于MAC帧进行校验解析后，根据解析到的MSDU类型，可以将解析出来的MSDU帧，通过MSDU接收原语，交由相应的业务应用处理。

## 5424 业务注册请求原语

## 54241 原语定义

应用层业务，通过业务注册请求原语，完成对数据链路层数据传输服务的注册使用。业务注册请求原语的语义如表160所示。

<div style="text-align: center;">表 160 业务注册请求原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU 类型</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>48 255</td><td style='text-align: center; word-wrap: break-word;'>业务申请的 MSDU 类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>缺省优先级</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>业务报文的缺省优先级</td></tr></table>

## 54242 数据链路层处理

数据链路层根据既定的业务类型规划，以及已完成确认的业务注册情况，处理业务注册请求原语。

数据链路层对于业务注册请求中的需求，存在批准和不批准两种可能。

数据链路层对于业务注册请求原语，通过业务注册确认原语进行确认。

## 5425 业务注册确认原语

## 54251 原语定义

数据链路层，通过业务注册确认原语，完成对应用层业务的注册请求的确认。业务注册确认原语的语义如表161所示。

<div style="text-align: center;">表 161 业务注册确认原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>确认结果</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 2</td><td style='text-align: center; word-wrap: break-word;'>0。表示按注册请求批准；\n1。表示按实际分配批准；\n2。表示未批准。注册失败</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MSDU 类型</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>48 255</td><td style='text-align: center; word-wrap: break-word;'>批准的 MSDU 类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>缺省优先级</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>批准的报文缺省优先级</td></tr></table>

## 54252 数据链路层处理

数据链路层通过业务注册确认原语，对业务注册请求原语进行确认。

## 5426 业务LID申请原语

## 54261 原语定义