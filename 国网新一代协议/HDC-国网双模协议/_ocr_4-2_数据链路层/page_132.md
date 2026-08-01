## 543 数据链路层数据管理服务

## 5431 数据管理原语分类

数据链路层的数据管理服务原语一共有10个，如表165所示。

<div style="text-align: center;">表165 数据链路层数据管理服务原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>原语名称</td><td style='text-align: center; word-wrap: break-word;'>功能</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络拓扑查询原语</td><td style='text-align: center; word-wrap: break-word;'>查询 CCO 的网络拓扑信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络拓扑上报原语</td><td style='text-align: center; word-wrap: break-word;'>上报 CCO 的网络拓扑信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络 NID 查询原语</td><td style='text-align: center; word-wrap: break-word;'>查询 CCO 的 NID 信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络 NID 上报原语</td><td style='text-align: center; word-wrap: break-word;'>上报 CCO 的 NID 信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络 NID 设置原语</td><td style='text-align: center; word-wrap: break-word;'>设置 CCO 的 NID 信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络查询原语</td><td style='text-align: center; word-wrap: break-word;'>查询 CCO 的邻居网络信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络上报原语</td><td style='text-align: center; word-wrap: break-word;'>上报 CCO 的邻居网络信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单查询原语</td><td style='text-align: center; word-wrap: break-word;'>查询 CCO 的白名单信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单上报原语</td><td style='text-align: center; word-wrap: break-word;'>上报 CCO 的白名单信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单设置原语</td><td style='text-align: center; word-wrap: break-word;'>设置 CCO 的白名单信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道组查询原语</td><td style='text-align: center; word-wrap: break-word;'>查询 CCO 的无线信道组信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道组上报原语</td><td style='text-align: center; word-wrap: break-word;'>上报 CCO 的无线信道组信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道组设置原语</td><td style='text-align: center; word-wrap: break-word;'>设置 CCO 的无线信道组信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道查询原语</td><td style='text-align: center; word-wrap: break-word;'>查询 CCO 的无线信道编号信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道上报原语</td><td style='text-align: center; word-wrap: break-word;'>上报 CCO 的无线信道编号信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道设置原语</td><td style='text-align: center; word-wrap: break-word;'>设置 CCO 的无线信道编号信息</td></tr></table>

## 5432 网络拓扑查询原语

## 54321 原语定义

应用层可通过网络拓扑查询原语获取当前网络中入网站点的拓扑信息，网络拓扑查询原语的语义如表166所示。

<div style="text-align: center;">表 166 网络拓扑查询原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>起始序列号</td><td style='text-align: center; word-wrap: break-word;'>2 字节序号</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>请求有效拓扑表项的起始序列号</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>请求表项数量</td><td style='text-align: center; word-wrap: break-word;'>2 字节数量</td><td style='text-align: center; word-wrap: break-word;'>1 1024</td><td style='text-align: center; word-wrap: break-word;'>本次请求的有效表项数量</td></tr></table>

## 54322 数据链路层处理

数据链路层对于当前网络拓扑中的有效表项信息，根据网络查询原语的要求，使用网络拓扑上报顺序上报。

## 5433 网络拓扑上报原语

## 54331 原语定义