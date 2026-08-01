<div style="text-align: center;"><img src="imgs/img_in_image_box_183_200_1032_464.jpg" alt="Image" width="71%" /></div>


<div style="text-align: center;">图 59 上行接收率老化示例 2</div>


接收率窗口为4，K+1周期到K+5周期，节点A和B通信中断，K+6周期开始节点A到B单向通信。接收率变化如表155所示。

<div style="text-align: center;">表 155 示例 2 上行接收率老化表</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td rowspan="2">周期</td><td colspan="2">A节点（统计与B节点通信率）</td><td colspan="3">B节点（统计与A节点通信率）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>下行</td><td style='text-align: center; word-wrap: break-word;'>上行</td><td style='text-align: center; word-wrap: break-word;'>下行</td><td style='text-align: center; word-wrap: break-word;'>上行</td><td style='text-align: center; word-wrap: break-word;'>上行（无老化）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+1</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>75</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+2</td><td style='text-align: center; word-wrap: break-word;'>75</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>50</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+3</td><td style='text-align: center; word-wrap: break-word;'>50</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>25</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+4</td><td style='text-align: center; word-wrap: break-word;'>25</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>100</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+5</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+6</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>25</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>K+7</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>50</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>100</td></tr></table>

对于节点A，从K+5周期，统计与邻居节点B的通信率为0，则不在发现列表中携带节点的上行接收率。当K+6周期，节点A和B之间单向通信时，节点B无法通过节点发送的无线发现列表报文更新与节点A的上行接收率。

## 534105 无线接收率交换

节点创建无线发现列表报文时，根据最近接收到的无线发现列表报文计算与邻居节点的下行接收率。因此节点在无线发现列表报文中携带与邻居节点的接收率都是最近统计到的信息。交换的示意图如图60所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_257_1240_959_1355.jpg" alt="Image" width="58%" /></div>


<div style="text-align: center;">图 60 无线接收率交换内容示意图</div>


假设接收位图大小为8，与节点i的接收率在周期K时，统计到接收到8个节点i的通信率采样报文，则在发现列表报文中携带与节点i的接收率为100；若在周期K+1时，统计接收到7个节点i的通