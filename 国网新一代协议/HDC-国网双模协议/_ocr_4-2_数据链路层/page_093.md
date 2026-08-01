<div style="text-align: center;"><img src="imgs/img_in_image_box_360_191_851_856.jpg" alt="Image" width="41%" /></div>


<div style="text-align: center;">源站点</div>


<div style="text-align: center;">图 29 报文过滤示意图</div>


## 528 单播/广播

对于SOF帧，在高速载波通信网络中发送时，可采用单播和广播机制，来控制报文转发的范围。单播报文和广播报文通过SOF帧的“帧控制”中的“广播标志位”字段来区别。

单播方式，是指报文发送时，通过SOF帧“帧控制”的“目的TEI”来指定了具体的接收站点，其他站点从线路上检出单播报文时，如果“目的TEI”不是本站点，则不需要处理。

单播报文收发的示意图如图30所示。CCO发送的报文，指定目的地址是STA1时，则PCO1也在可正确接收报文的范围内，但是不需要处理。