<div style="text-align: center;">表71 (续)</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x02</td><td style='text-align: center; word-wrap: break-word;'>表示该站点在黑名单中</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x03</td><td style='text-align: center; word-wrap: break-word;'>表示加入的站点个数超过上限</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x04</td><td style='text-align: center; word-wrap: break-word;'>表示没有设置白名单列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x05</td><td style='text-align: center; word-wrap: break-word;'>表示代理站点个数超过上限</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x06</td><td style='text-align: center; word-wrap: break-word;'>表示子站点个数超过上限</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x07</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x08</td><td style='text-align: center; word-wrap: break-word;'>表示重复的 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x09</td><td style='text-align: center; word-wrap: break-word;'>表示超过拓扑层级</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0A</td><td style='text-align: center; word-wrap: break-word;'>表示站点再次关联请求入网成功</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0B</td><td style='text-align: center; word-wrap: break-word;'>表示新的站点试图以自己的子站点为代理来入网</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0C</td><td style='text-align: center; word-wrap: break-word;'>表示组网拓扑中存在环路</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0D</td><td style='text-align: center; word-wrap: break-word;'>表示 CCO 端未知原因出错</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0E</td><td style='text-align: center; word-wrap: break-word;'>表示无线代理达到上限</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51335 站点层级

表示站点入网后的所处拓扑层级。

## 51336 站点TEI

CCO在确认该站点可以入网后，为该站点分配的设备标识TEI。

## 51337 链路类型

表示代理与关联确认目标站点的通信链路类型，链路类型值定义如表72所示。

<div style="text-align: center;">表72 链路类型值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>高速载波链路</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>无线链路</td></tr></table>

## 51338 载波频段

表示网络采用的载波频段，载波频段值定义如表73所示。

<div style="text-align: center;">表 73 载波频段值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1.953~11.96</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>2.441~5.615</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0.781~2.930</td></tr></table>