<div style="text-align: center;">表126（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>链路最小接收率</td><td style='text-align: center; word-wrap: break-word;'>11</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线发现列表周期</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线接收率老化周期个数</td><td style='text-align: center; word-wrap: break-word;'>13</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

## 513238 站点路由信息格式

表示站点多路径信息，站点路由信息格式如表127所示。

<div style="text-align: center;">表 127 站点路由信息格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td rowspan="2">下一跳站点 TEI[1]</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td rowspan="2">1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由类型[1]</td><td style='text-align: center; word-wrap: break-word;'>0 4</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td></tr><tr><td rowspan="2">下一跳站点 TEI[N]</td><td style='text-align: center; word-wrap: break-word;'>2N 2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td rowspan="2">2N 1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>路由类型[N]</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr></table>

路由类型定义如表98所示。同级路由，指使用与本站点层级相同站点，作为下一跳路由站点；上级路由，指使用比本站点低一个层级的站点，作为下一跳路由站点；代理主路径路由，指使用本站点的代理站点，作为下一跳路由站点；上上级路由，指使用比本站点低两个层级的站点，作为下一条路由站点。

## 5 1 3 23 9 邻居节点信道信息非位图格式

邻居节点信道信息非位图格式如表128所示。

<div style="text-align: center;">表 128 邻居节点信道信息非位图格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信道信息组合类型</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居节点信道信息 $ ^{[1]} $</td><td style='text-align: center; word-wrap: break-word;'>可变长</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>可变长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td><td style='text-align: center; word-wrap: break-word;'>... ...</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居节点信道信息 $ ^{[N]} $</td><td style='text-align: center; word-wrap: break-word;'>可变长</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>可变长</td></tr></table>

信道信息组合类型取值和含义如表129所示。