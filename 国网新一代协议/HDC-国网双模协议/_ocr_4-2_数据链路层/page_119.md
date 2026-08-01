对于上行通信变差时，接收不到邻居节点报文。或者邻居节点已经判定本节点的接收率为0，不在发布本节点的接收率，则无法通过邻居节点发现列表消息更新上行接收率，因此需要一种老化机制，保证在这种场景下，能够将上行接收率的更新。

上行接收率老化机制：N个发现列表周期未对上行接收率进行更新，则将上行接收率更新为0。（上行接收率老化周期个数N由CCO选择，通过无线路由参数条目通知到网络中每一个节点）。上行接收率老化示例1如图58所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_240_390_1004_645.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 58 上行接收率老化示例 1</div>


窗口大小为4，上行接收率老化周期数为4。从周期K+1开始，节点A到节点B可以通信，节点B到节点A通信中断。节点A和B接收率变化如表154所示。

<div style="text-align: center;">表 154 示例 1 上行接收率交换老化表</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td rowspan="2">周期</td><td colspan="2">A节点（统计与B节点通信率）</td><td colspan="2">B节点（统计与A节点通信率）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>下行</td><td style='text-align: center; word-wrap: break-word;'>上行</td><td style='text-align: center; word-wrap: break-word;'>下行</td><td style='text-align: center; word-wrap: break-word;'>上行</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+1</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+2</td><td style='text-align: center; word-wrap: break-word;'>75</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>75</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+3</td><td style='text-align: center; word-wrap: break-word;'>50</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>50</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+4</td><td style='text-align: center; word-wrap: break-word;'>25</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>25</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+5</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr></table>

节点A：

从K+1周期开始，与节点B的下行接收率每个周期下降25，到K+5周期下行接收率降低为0。由于无法接收到B的无线发现列表报文，因此无法更新上行接收率，根据上行接收率的老化机制，到K+5周期时，节点已经连续4个周期未更新上行接收率，因此老化为0。

节点B：

与节点A的下行通信良好，因此保持不变。

上行接收率通过节点A的无线发现列表，每个周期更新一次，则到K+5周期时，更新为0x

上行接收率老化示例2如图59所示。