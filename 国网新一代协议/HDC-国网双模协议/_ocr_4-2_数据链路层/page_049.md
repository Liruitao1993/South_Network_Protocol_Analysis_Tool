站点表的信息，每一个分包的路由表项都要保证能够无歧义解析。所有分包中，需要顺序先传输直连子站点，直连子站点未满一个分包，可继续传输直连代理子站点及其子站点；如果一个代理站点的子站点数量过大，需要多个分包时，每个分包的第一个表项必须填写该代理子站点，第二表项填写该分包中该代理站点子站点的数量，即所有分包中传输直连代理站点及其子站点时，必须保证如下格式顺序：直连代理站点TEI，该代理站点下子站点数量，子站点TEI。

## 5134 关联汇总指示报文

## 51341 关联汇总指示格式

关联汇总指示报文（MMeAssocGatherInd）格式的定义如表76所示。

<div style="text-align: center;">表 76 关联汇总指示报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>结果</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点层级</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CCO MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>2 7</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td rowspan="2">代理 TEI</td><td style='text-align: center; word-wrap: break-word;'>8</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12 比特</td></tr><tr><td rowspan="3">9</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>载波频段</td><td style='text-align: center; word-wrap: break-word;'>4 5</td><td style='text-align: center; word-wrap: break-word;'>2 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>6 7</td><td style='text-align: center; word-wrap: break-word;'>2 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>10</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>汇总站点数</td><td style='text-align: center; word-wrap: break-word;'>11</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>12 15</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点信息</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 51342 结果

表示关联请求的结果，固定值为0，表示允许加入网络。

## 51343 站点层级

表示所有新入网站点所处的网络层级

## 51344 CCO MAC 地址

表示本网络中CCO的设备MAC地址。

## 51345 代理TEI

表示代理站点的设备标识，为所通知的所有新入网站点的代理站点的TEI。

## 51346 载波频段

表示网络采用的载波频段，载波频段值定义如表77所示。