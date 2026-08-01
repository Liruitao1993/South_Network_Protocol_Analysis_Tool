## 5437 邻居网络查询原语

## 54371 原语定义

应用层通过邻居网络查询原语，查询CCO的邻居网络信息。邻居网络查询原语的语义如表172所示。

<div style="text-align: center;">表 172 邻居网络信息查询原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

## 54372 数据链路层处理

数据链路层在接收到邻居网络查询原语后，需要通过邻居网络信息上报原语，给应用层提交本网络的邻居网络信息。

## 5438 邻居网络上报原语

## 54381 原语定义

应用层通过邻居网络查询原语查询邻居网络信息时，数据链路层通过邻居网络上报原语上报邻居网络信息 $ ^{x} $。邻居网络上报原语的语义如表173所示。

<div style="text-align: center;">表 173 邻居网络上报原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>表项总数</td><td style='text-align: center; word-wrap: break-word;'>1 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 31</td><td style='text-align: center; word-wrap: break-word;'>邻居网络信息表项总数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络信息</td><td style='text-align: center; word-wrap: break-word;'>可变长字节流</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>邻居网络单个表项的信息:\n数据总大小。由表项总数 * 单个表项大小。\n单个表项的数据大小请参照表174</td></tr></table>

<div style="text-align: center;">表 174 网络拓扑上报单个表项信息原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>NID</td><td style='text-align: center; word-wrap: break-word;'>3 字节</td><td style='text-align: center; word-wrap: break-word;'>1 16777215</td><td style='text-align: center; word-wrap: break-word;'>邻居网络的网络标识</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>单通标志</td><td style='text-align: center; word-wrap: break-word;'>布尔</td><td style='text-align: center; word-wrap: break-word;'>0 或者 1</td><td style='text-align: center; word-wrap: break-word;'>与本网络是否为单通：\n1 为单通；\n0 为双通</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>占用带宽</td><td style='text-align: center; word-wrap: break-word;'>4 字节</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>邻居网络占用的带宽。单位毫秒</td></tr></table>

## 54382 数据链路层处理

数据链路层对于当前CCO中多网络有效表项，根据邻居网络查询原语的要求，使用邻居网络上报原语顺序上报。