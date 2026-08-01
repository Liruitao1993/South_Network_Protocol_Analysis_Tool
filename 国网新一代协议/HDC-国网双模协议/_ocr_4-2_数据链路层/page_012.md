## 51139 重启次数

指站点的重启次数。当一个站点初次上电时，重启次数的值缺省为0，此后，每次站点重新上电，该值加1，仅用于MAC帧唯一性辅助判断。该值在0 15的范围内变化，达到最大值时，从0开始重新递增。

## 5 1 1 3 10 代理主路径标识

当前报文是否根据代理主路径模式进行转发的标志，含义如表6所示。

<div style="text-align: center;">表6 代理主路径</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>未启用代理主路径模式</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>当前使用代理主路径模式</td></tr></table>

## 511311 路由总跳数

路由总跳数指MAC帧可以被转发的总跳数。报文在转发过程中，该字段的值不能修改，保持与原报文数值一致。

## 5 1 1 3 12 路由剩余跳数

路由剩余跳数指MAC帧可以被转发的剩余跳数。每个站点确定需要转发时，需要对该值减1。当该值减为0时，则该报文不能再进行转发。

## 511313 广播方向

广播报文的传输方向，含义如表7所示。

<div style="text-align: center;">表7 广播方向</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>双向广播（不限定方向）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>下行广播（从 CCO 发起广播至 STA）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>上行广播（从 STA 发起广播至 CCO）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 511314 路径修复标志

路径修复标志，标识本帧报文在传输中是否触发过路径修复。1代表已触发过路径修复过程，0代表未触发过路径修复，含义如表8所示。

<div style="text-align: center;">表8 路径修复标志</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>当前报文未触发过路径修复</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>当前报文已触发过路径修复</td></tr></table>