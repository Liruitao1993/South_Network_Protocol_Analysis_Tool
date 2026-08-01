无线发现列表中报文增加 “统计序号”，统计序号定义为 “Seq”，该序号用于对无线发现列表报文的统计。

节点为每一个邻居节点建立一个无线邻居节点信息表项，表项中包含发现列表报文接收位图，位图大小定义为K，位图更新索引为UpdateIndex。无线邻居节点信息表项如表153所示。

<div style="text-align: center;">表 153 无线邻居节点信息表项</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段名称</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>UpdateIndex</td><td style='text-align: center; word-wrap: break-word;'>RcvMap更新的索引</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>RcvMap</td><td style='text-align: center; word-wrap: break-word;'>无线发现列表报文接收位图</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>UpRcvRate</td><td style='text-align: center; word-wrap: break-word;'>上行通信率采样报文接收率，通过发现列表交换获取</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>NotUpdateCnt</td><td style='text-align: center; word-wrap: break-word;'>上行接收率未更新的周期数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DownRssi</td><td style='text-align: center; word-wrap: break-word;'>下行信号强度，通过接收邻居节点的报文获取。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DownSnr</td><td style='text-align: center; word-wrap: break-word;'>下行平均信噪比，通过接收邻居节点的报文获取。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>UpRssi</td><td style='text-align: center; word-wrap: break-word;'>上行信道强度，通过发现列表报文交换获取。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>UpSnr</td><td style='text-align: center; word-wrap: break-word;'>上行平均信噪比，通过发现列表报文交换获取。</td></tr></table>

通信率统计采样报文的统计序号为8比特，表示范围为0到255，因此建议位图大小K的大小可以选择8e 16e 32e

接收到一个无线发现列表报文，其中统计序号为Seq，那么对应的UpdateIndex（rcv）=Seq%K∗ 将 Rcvmap中对应UpdateIndex（rcv）比特位置为1✗

更新场景1：连续接收到无线发现列表报文，更新如图50所示。

条件：UpdateIndex（rcv）=（UpdateIndex+1）%K。

更新动作：UpdateIndex更新为UpdateIndex（rcv）%K。

<div style="text-align: center;"><img src="imgs/img_in_image_box_351_919_868_1090.jpg" alt="Image" width="43%" /></div>


<div style="text-align: center;">图 50 连续接收更新示意图</div>


更新场景2：无线发现列表报文出现丢失，更新如图51所示。

条件：UpdateIndex（rcv）>UpdateIndex+1。

更新动作：将UpdateIndex+1到UpdateIndex（rcv）1之间的位图更新为0，并且将UpdateIndex更新为UpdateIndex（rcv）%K∗

<div style="text-align: center;"><img src="imgs/img_in_image_box_352_1293_869_1466.jpg" alt="Image" width="43%" /></div>


<div style="text-align: center;">图 51 丢失更新示意图</div>
