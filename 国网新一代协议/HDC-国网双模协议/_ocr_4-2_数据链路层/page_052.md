表示申请代理变更站点的原代理站点的设备标识。

## 51356 代理类型

表示申请代理变更站点的原代理类型，定义如表81所示。

<div style="text-align: center;">表81 代理类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示站点动态选择的代理</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51357 原因

表示站点发起代理变更原因，定义如表82所示。

<div style="text-align: center;">表82 代理变更原因</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>未知</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>表示周期代理变更</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51358 站点相线

表示发起代理变更请求站点的相线信息，最低字节存放评估出的所属相线，其他字节依次填入可能的备选相位，相线的值定义如表83所示。

<div style="text-align: center;">表 83 相线评估信息</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示未知相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>表示A相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>表示B相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>表示C相线</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>无效</td></tr></table>

## 51359 端到端序列号

表示端到端的报文序列号。

请求代理变更的站点，在产生代理变更请求报文时，需要获取一个序列号，CCO在确认代理变更时，需要在确认报文中携带代理变更请求报文中的端到端报文序列号。

该序列号由发起请求的站点维护。

## 5136 代理变更请求确认报文

## 5 1 3 6 1 代理变更请求确认报文格式