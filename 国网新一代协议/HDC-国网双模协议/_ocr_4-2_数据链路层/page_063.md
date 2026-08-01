## 51312 网络冲突上报报文

## 513121 网络冲突上报报文格式

网络冲突上报报文（MMeNetworkConflictReport）格式的定义如表102所示。该报文在STA识别出存在NID重复后，上报至CCO，CCO可根据冲突网络信息进行NID调整。

<div style="text-align: center;">表 102 网络冲突上报报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td rowspan="6">CCO MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>0</td><td rowspan="6">6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络个数</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络号字节宽度</td><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络条目</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 513122 CCO MAC 地址

表示与本网络发生冲突的邻居网络的CCO MAC地址。

## 5 1 3 12 3 邻居网络个数

周边可见邻居网络的个数。

## 513124 网络号字节宽度

网络号的字节宽度，单位是字节。本协议中网络号字节宽度默认为3。

## 5 1 3 12 5 邻居网络条目

邻居网络信息，具体如表103所示。

<div style="text-align: center;">表 103 邻居网络条目</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络（0）</td><td style='text-align: center; word-wrap: break-word;'>0 2</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络（1）</td><td style='text-align: center; word-wrap: break-word;'>3 5</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络（N）</td><td style='text-align: center; word-wrap: break-word;'>3N (3N+2)</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr></table>

## 51313 过零 NTB 采集指示报文

## 513131 过零 NTB 采集指示报文格式

过零NTB采集指示报文（MMeZeroCrossNTBCollectInd）格式的定义如表104所示。