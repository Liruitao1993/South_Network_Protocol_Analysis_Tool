## 513141 过零 NTB 告知报文格式

过零NTB告知报文（MMeZeroCrossNTBReport）格式的定义如表107所示。本报文可由STA站点或者CCO站点创建发送。

<div style="text-align: center;">表 107 过零 NTB 告知报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td rowspan="2">TEI</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>07</td><td rowspan="2">12 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>03</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>47</td><td style='text-align: center; word-wrap: break-word;'>4 比特</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>告知总数量</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 1 差值告知数量</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 2 差值告知数量</td><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 3 差值告知数量</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>基准 NTB</td><td style='text-align: center; word-wrap: break-word;'>69</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 1 过零 NTB 差值</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L (可变长)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 2 过零 NTB 差值</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L (可变长)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相线 3 过零 NTB 差值</td><td style='text-align: center; word-wrap: break-word;'>可变</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>L (可变长)</td></tr></table>

## 513142 TEI

表示告知过零NTB信息的站点。

## 513143 告知总数量

表示站点告知的过零NTB的数量。

## 513144 相线差值告知数量

表示站点告知相应相线的过零NTB差值的数量。

## 513145 基准NTB

表示站点告知的基准NTB。该NTB是站点告知的第一个过零点NTB值，是后续过零NTB用来计算差值的基准NTB。该字段保存的NTB值，是采集的过零点NTB值原始32比特数据，右移8比特之后的数据，相当于原始数据的高24比特数据。

## 513146 相线过零 NTB 差值

表示每个相线的过零NTB与前一个NTB的差值的全部数据，按照相线13的顺序依次保存。

过零NTB差值的计算方法：以基准NTB为开始，后续的每一个过零NTB，都与前一个NTB做差值计算；将计算得到的差值数据，右移8bit，只保留高比特位的部分。

将最终得到的差值，作为过零NTB差值，按照时间顺序，存入“过零NTB差值”字段，上报CCO

说明：在电力线的工频周期中，过零点的间隔一般在10毫秒左右，两个过零点之间的NTB差值不会超过20个比特位的表示区间。所以，过零点NTB差值，在右移8比特后，需要用12比特的字段来表示。

每个相线的过零NTB差值存储的定义如表108所示。