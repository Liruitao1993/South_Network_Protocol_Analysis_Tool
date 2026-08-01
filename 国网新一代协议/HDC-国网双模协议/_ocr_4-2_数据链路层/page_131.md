应用层业务，通过业务LID申请原语，进行业务分类LID的申请。业务LID申请原语的语义如表162所示。

<div style="text-align: center;">表 162 业务 LID 申请原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>业务 LID</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>4 254</td><td style='text-align: center; word-wrap: break-word;'>应用层业务申请的业务LID</td></tr></table>

## 54262 数据链路层处理

数据链路层根据既定的LID规划，以及已完成的LID批准情况，完成对业务LID申请原语的处理。

数据链路层对业务LID申请，存在批准和不批准两种情况。

数据链路层对已经分配的LID，不会进行二次分配，除非该LID被释放。

数据链路层对业务LID申请原语，使用业务LID确认原语完成确认。

## 5427 业务LID确认原语

## 54271 原语定义

数据链路层，通过业务注册确认原语，完成对应用层业务的注册请求的确认。业务LID确认原语的语义如表163所示。

<div style="text-align: center;">表 163 业务 LID 确认原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>确认结果</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 2</td><td style='text-align: center; word-wrap: break-word;'>0。表示申请需求批准；\n1。表示按实际分配批准；\n2。表示未批准。申请失败</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>业务 LID</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>4 254</td><td style='text-align: center; word-wrap: break-word;'>批准的业务 LID</td></tr></table>

## 54272 数据链路层处理

数据链路层通过业务LID确认原语，对业务LID申请原语进行确认。

## 5428 业务LID释放原语

## 54281 原语定义

应用层业务通过业务LID释放原语完成对业务LID的释放。业务LID释放原语的语义如表164所示。

<div style="text-align: center;">表 164 业务 LID 释放原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>业务 LID</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>4 254</td><td style='text-align: center; word-wrap: break-word;'>表示要释放的业务LID</td></tr></table>

## 54282 数据链路层处理

数据链路层根据业务LID释放原语，完成LID资源的回收后，可将该LID再次分配。