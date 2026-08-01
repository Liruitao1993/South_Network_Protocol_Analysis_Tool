## 54341 原语定义

应用层通过网络NID查询原语，查询CCO的网络NID。网络NID查询原语的语义如表169所示。

<div style="text-align: center;">表 169 网络 NID 查询原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

## 54342 数据链路层处理

数据链路层在接收到网络NID查询原语后，需要通过网络NID上报原语，向应用层提交本网络的NID信息。

## 5435 网络 NID 上报原语

## 54351 原语定义

数据链路层通过网络NID上报原语，向应用层上报本网络的NID信息。网络NID上报原语的语义如表170所示。

<div style="text-align: center;">表 170 网络 NID 上报原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络 NID</td><td style='text-align: center; word-wrap: break-word;'>3 字节</td><td style='text-align: center; word-wrap: break-word;'>1 16777215</td><td style='text-align: center; word-wrap: break-word;'>本网络的 NID</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线信道编号</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td><td style='text-align: center; word-wrap: break-word;'>0 255</td><td style='text-align: center; word-wrap: break-word;'>无线信道编号</td></tr></table>

## 54352 数据链路层处理

数据链路层在接收到网络NID查询原语后，必须通过网络NID上报原语，向应用层提交本网络的NID信息。

## 5436 网络 NID 设置原语

## 54361 原语定义

应用层可以通过网络NID设置原语，要求数据链路层修改本网络的NID。网络NID设置原语的语义如表171所示。

<div style="text-align: center;">表 171 网络 NID 设置原语</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>有效范围</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络 NID</td><td style='text-align: center; word-wrap: break-word;'>3 字节</td><td style='text-align: center; word-wrap: break-word;'>1 16777215</td><td style='text-align: center; word-wrap: break-word;'>本网络的新的 NID</td></tr></table>

## 54362 数据链路层处理

数据链路层在接收网络NID设置原语后，需要将本网络的NID设置为网络NID设置原语中的网络NID。