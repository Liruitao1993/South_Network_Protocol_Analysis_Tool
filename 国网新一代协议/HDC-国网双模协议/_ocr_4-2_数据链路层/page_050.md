<div style="text-align: center;">表 77 载波频段值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1.953~11.96</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>2.441~5.615</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0.781~2.930</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>1.758~2.930</td></tr></table>

## 51347 汇总站点数

表示关联汇总指示报文中通知的新入网站点的个数。

按照长帧头或短帧头，分别允许最大可支持58和59。

## 51348 站点信息

表示关联汇总指示报文中，所有新入网站点的信息。

站点信息字段的定义如表78所示。

<div style="text-align: center;">表 78 站点信息字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点 MAC 地址 1</td><td style='text-align: center; word-wrap: break-word;'>0 5</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>6 字节</td><td style='text-align: center; word-wrap: break-word;'>站点的 MAC 地址</td></tr><tr><td rowspan="2">站点 TEI1</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td><td rowspan="2">分配给站点的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点 MAC 地址 2</td><td style='text-align: center; word-wrap: break-word;'>8 13</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>6 字节</td><td style='text-align: center; word-wrap: break-word;'>站点的 MAC 地址</td></tr><tr><td rowspan="2">站点 TEI2</td><td style='text-align: center; word-wrap: break-word;'>14</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td><td rowspan="2">分配给站点的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>15</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>15</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点 MAC 地址 N</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>站点的 MAC 地址\nN=汇总站点数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点 TEIN</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>--</td><td style='text-align: center; word-wrap: break-word;'>分配给站点的 TEIN\nN=汇总站点数</td></tr></table>

## 5135 代理变更请求报文

## 51351 代理变更请求报文格式

代理变更请求报文（MMeChangeProxyReq）格式的定义如表79所示。

<div style="text-align: center;">表 79 代理变更请求报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小</td></tr><tr><td rowspan="2">站点 TEI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr></table>