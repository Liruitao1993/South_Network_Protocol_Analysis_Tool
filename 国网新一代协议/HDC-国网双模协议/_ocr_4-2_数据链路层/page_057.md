<div style="text-align: center;">表92（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>CCO 判断网络拓扑的层级超过上限</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>CCO 判断站点不在最新的白名单中</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51383 站点总数

表示CCO告知的需要离线的站点个数。

## 51384 延迟时间

表示需要离线的站点可以在延迟时间到期后离线。单位为秒。

## 51385 站点 MAC 地址

包含离线站点的MAC地址，是可变长度字段，根据离线站点数目的不同，长度可变。定义如表93所示。

<div style="text-align: center;">表93 站点 MAC 地址字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小(byte)</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC[0]</td><td style='text-align: center; word-wrap: break-word;'>0 5</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>需要离线站点的 MAC</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC[1]</td><td style='text-align: center; word-wrap: break-word;'>6 11</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>需要离线站点的 MAC</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>需要离线站点的 MAC</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>MAC[N 1]</td><td style='text-align: center; word-wrap: break-word;'>(6*(N 1)) (6*(N 1) +5)</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>需要离线站点的 MAC\nN=站点总数</td></tr></table>

## 5139 心跳检测报文

## 51391 心跳检测报文格式

心跳检测报文（MMeHeartBeatCheck）格式的定义如表94所示。

<div style="text-align: center;">表 94 心跳检测报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td rowspan="2">原始源 TEI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td rowspan="2">发现站点数最大的站点\nTEI</td><td style='text-align: center; word-wrap: break-word;'>2 3</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr></table>