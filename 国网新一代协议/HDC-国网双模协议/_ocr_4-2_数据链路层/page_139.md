应用层可以通过无线信道查询原语，获得当前CCO的无线信道编号x，无线信道编号查询原语的语义定义如表181所示。

<div style="text-align: center;">表 181 无线信道查询原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

## 543152 数据链路层处理

数据链路层在接收到无线信道查询原语后，需要通过无线信道上报原语，向应用层提交本网络的无线信道编号信息。

## 54316 无线信道上报原语

## 543161 原语定义

数据链路层通过无线信道上报原语，向应用层上报本网络的无线信道信息。无线信道上报原语的语义如表182所示。

<div style="text-align: center;">表 182 无线信道上报原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号</td><td style='text-align: center; word-wrap: break-word;'>1字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>本网络的无线信道编号</td></tr></table>

## 543162 数据链路层处理

数据链路层接收到无线信道查询原语后，必须通过无线信道上报原语，向应用层提交本网络的无线信道编号信息。

## 54317 无线信道设置原语

## 543171 原语定义

应用层可以通过无线信道设置原语，要求数据链路层修改本网络的无线信道编号。无线信道设置原语的定义如表183所示。

<div style="text-align: center;">表 183 无线信道设置原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号</td><td style='text-align: center; word-wrap: break-word;'>1字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>本网络的无线信道编号</td></tr></table>

## 543172 数据链路层处理

数据链路层接收到无线信道设置原语后，需要将本网络的无线信道编号设置为无线信道设置原语中的无线信道编号。