<div style="text-align: center;">表94（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大的发现站点数</td><td style='text-align: center; word-wrap: break-word;'>45</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>位图大小</td><td style='text-align: center; word-wrap: break-word;'>67</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>发现站点位图</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 51392 原始源 TEI

设置为初始产生心跳检测报文的站点的TEI，该报文被各级代理转发时，OSTEI不变更。

## 51393 发现站点数最大的站点 TEI

表示发现站点数量最多的站点的TEI。心跳检测报文被转发给CCO时，本字段记录的是沿途转发站点中，发现周围站点数量最多的站点的TEI。

## 51394 最大的发现站点数

表示最大的发现站点数量。心跳检测报文被转发给CCO时，本字段记录的是沿途转发站点中，发现站点数最大的站点所发现的周围站点的数量。

## 51395 位图大小

表示“发现站点位图”字段的大小，单位是字节。

## 51396 发现站点位图

表示可发现的站点的TEI，按照位图的形式表示。这里的可发现站点，是心跳报文传输过程中，对各个站点的发现站点的汇总表示。根据TEI大小在位图中相应的位置上填写标志，当比特位的值为1时，表示对应的TEI有效。如第0字节的第1比特值为1，表示可以发现TEI为1的站点；第1字节的第0比特值为1，表示可以发现TEI为8的站点。

## 5 1 3 10 发现列表报文

## 5 1 3 10 1 发现列表报文格式

发现列表报文（MMeDiscoverNodeList）格式的定义如表95所示。

<div style="text-align: center;">表95 发现列表报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td></tr><tr><td rowspan="2">TEI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td rowspan="2">代理 TEI</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td rowspan="2">12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>角色</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>层级</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>4 9</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>48</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CCO MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>10 15</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>48</td></tr></table>