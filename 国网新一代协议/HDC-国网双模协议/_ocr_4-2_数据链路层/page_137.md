应用层可以通过白名单设置原语，要求CCO的数据链路层更新本地的白名单表项。白名单上报原语的语义如表177所示。

<div style="text-align: center;">表177 白名单上报原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>操作标志</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>本次白名单设置的动作：\n0x00 $ _{i} $ 关闭白名单；\n0x01 $ _{i} $ 添加白名单；\n0x02 $ _{i} $ 删除白名单</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次设置总数</td><td style='text-align: center; word-wrap: break-word;'>2 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>本次设置的白名单表项数量</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址 1</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址 2</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址 n</td><td style='text-align: center; word-wrap: break-word;'>6 字节 MAC</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>白名单 MAC 地址 $ _{i} $\n其中 n 为本次设置总数</td></tr></table>

## 543112 数据链路层处理

数据链路层根据白名单设置原语中的操作标志，将白名单MAC地址添加进白名单表项，或者将白名单中已经存在的表项删除。

## 54312 无线信道组查询原语

## 543121 原语定义

应用层可以通过无线信道组查询原语，获取当前CCO中的无线信道组。无线信道查询原语的定义如表178所示。

<div style="text-align: center;">表 178 无线信道组查询原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>起始序列号</td><td style='text-align: center; word-wrap: break-word;'>2 字节序号</td><td style='text-align: center; word-wrap: break-word;'>1 255</td><td style='text-align: center; word-wrap: break-word;'>请求有效无线信道组表项的起始序列号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>请求表项数量</td><td style='text-align: center; word-wrap: break-word;'>2 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 255</td><td style='text-align: center; word-wrap: break-word;'>本次请求的有效表项数量</td></tr></table>

## 543122 数据链路层处理

数据链路层接收到无线信道组查询原语，根据原语要求，使用无线信道组查询原语上报无线信道组表中的无线信道编号。

## 54313 无线信道组上报原语

## 543131 原语定义

应用层通过无线信道组查询原语查询CCO中可用的无线信道信息时，数据链路层通过无线信道组上报原语上报CCO中的可用无线信道组信息。无线信道组上报原语定义如表179所示。