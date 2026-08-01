更新场景3：无线发送列表报文发送延迟，更新如图52所示。

条件：UpdateIndex（rcv） <= UpdateIndex，并且RcvMap[UpdateIndex] = 0。

更新动作：将UpdateIndex = UpdateIndex（Rcv）。

<div style="text-align: center;"><img src="imgs/img_in_image_box_351_285_868_455.jpg" alt="Image" width="43%" /></div>


<div style="text-align: center;">图 52 发送延迟更新示意图</div>


更新场景4：无线发现列表报文乱序1，更新如图53所示。

条件：UpdateIndex（rcv）<UpdateIndex，并且RcvMap[UpdateIndex]=1。

更新动作：不更新UpdateIndex。

<div style="text-align: center;"><img src="imgs/img_in_image_box_350_628_869_796.jpg" alt="Image" width="43%" /></div>


<div style="text-align: center;">图 53 无线发现列表乱序 1 更新示意图</div>


更新场景5：无线发现列表报文乱序2，更新如图54所示。

条件：UpdateIndex（rcv）<UpdateIndex，并且RcvMap[UpdateIndex]=0。

更新动作：将UpdateIndex更新到最近一个RcvMap[i]等于1的值。

<div style="text-align: center;"><img src="imgs/img_in_image_box_350_971_869_1137.jpg" alt="Image" width="43%" /></div>


<div style="text-align: center;">图54 无线发现列表乱序2更新示意图</div>


## 534102 无线接收率的计算

无权重接收率 = 接收无线发现列表报文个数/窗口大小。接收率计算示例如图55。图56所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_178_1270_1033_1353.jpg" alt="Image" width="71%" /></div>


<div style="text-align: center;">图 55 无权重接收率窗口示意图</div>


窗口大小为8，有5个窗口接收到无线发现列表报文，则接收率 =5/8 =62.5%

有权重接收率计算：以 UpdateIndex 为基准点，将接收位图划分为 N 个段，分别计算每段的接收率，然后各段的接收率加权求和，距离 UpdateIndex 最近的段的权重最大，距离 UpdateIndex 最远的段的权重