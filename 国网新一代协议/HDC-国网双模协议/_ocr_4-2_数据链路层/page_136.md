## 5439 白名单查询原语

## 54391 原语定义

应用层可以通过白名单查询原语，获取当前CCO中的白名单信息。白名单查询原语的语义如表175所示。

<div style="text-align: center;">表 175 白名单查询原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>起始序列号</td><td style='text-align: center; word-wrap: break-word;'>2 字节序号</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>请求有效白名单表项的起始序列号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>请求表项数量</td><td style='text-align: center; word-wrap: break-word;'>2 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>本次请求的有效表项数量</td></tr></table>

## 54392 数据链路层处理

数据链路层对于当前CCO中有效的白名单表项，根据白名单查询原语的要求，使用白名单上报原语顺序上报。

## 54310 白名单上报原语

## 543101 原语定义

应用层通过白名单查询原语CCO的白名单信息时，数据链路层通过白名单上报原语上报CCO的白名单信息。白名单上报原语的语义如表176所示。

<div style="text-align: center;">表176 白名单上报原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>有效表项总数</td><td style='text-align: center; word-wrap: break-word;'>2 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>有效的白名单表项总数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次上报总数</td><td style='text-align: center; word-wrap: break-word;'>2 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>本次上报的有效表项数量</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上报结束标志</td><td style='text-align: center; word-wrap: break-word;'>布尔</td><td style='text-align: center; word-wrap: break-word;'>0 或者 1</td><td style='text-align: center; word-wrap: break-word;'>全部有效表项是否上报结束。\n1 表示上报结束；\n0 表示上报未结束。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址 1</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单中有效 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址 2</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单中有效 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单中有效 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址 n</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单中有效 MAC 地址\n其中 n 为本次上报总数</td></tr></table>

## 543102 数据链路层处理

数据链路层在接收到应用层的白名单查询原语后，通过白名单上报原语上报白名单信息 $ ^{x} $每个查询原语，发送一个上报原语 $ ^{x} $

## 54311 白名单设置原语

## 543111 原语定义