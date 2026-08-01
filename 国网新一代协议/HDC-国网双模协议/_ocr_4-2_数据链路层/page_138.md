<div style="text-align: center;">表 179 无线信道组上报原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>有效表项总数</td><td style='text-align: center; word-wrap: break-word;'>1 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>有效的无线信道表项总数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次上报总数</td><td style='text-align: center; word-wrap: break-word;'>1 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>本次上报的有效表项数量</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上报结束标志</td><td style='text-align: center; word-wrap: break-word;'>布尔</td><td style='text-align: center; word-wrap: break-word;'>0 或者 1</td><td style='text-align: center; word-wrap: break-word;'>全部有效表项是否上报结束。\n1 表示上报结束；\n0 表示上报未结束</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号 1</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>无线信道组中有效信道编号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号 2</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>无线信道组中有效信道编号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>无线信道组中有效信道编号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号 n</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>无线信道组中有效信道编号。\n其中 n 为本次上报总数</td></tr></table>

## 543132 数据链路层处理

数据链路层接收到应用层无线信道组查询原语后，通过无线信道组上报原语上报无线信道组信息。每个查询原语，发送一个上报原语。

## 54314 无线信道组设置原语

## 543141 原语定义

应用层可以通过无线信道设置原语，要求数据链路层配置网络可使用的无线信道组。无线信道组设置原语如表180所示。

<div style="text-align: center;">表 180 无线信道组设置原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>操作标志</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>本次无线信道组设置动作：\n0 表示添加无线信道；\n1 表示删除无线信道</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道组个数</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>1 255</td><td style='text-align: center; word-wrap: break-word;'>本次配置无线信道的个数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号 1</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>无线信道编号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>无线信道编号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号 n</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>无线信道编号。\n其中 n 为本次设置总数</td></tr></table>

## 543142 数据链路层处理

数据链路层根据无线信道组设置原语的操作标志，将无线信道编号添加到无线信道表项，或者将无线信道表中已经存在的表项删掉。

## 54315 无线信道查询原语

## 543151 原语定义