MSDU包含一个MSDU载荷或者一个管理消息。MAC帧是通过在每个MSDU载荷上预填充一个MAC帧头部，在尾部添加一个完整性校验值生成的，具体帧格式详见第5.1.1节。

MAC帧头部中的“MSDU长度”被设置为MSDU载荷的长度。“完整性校验”用于验证正确的解码和接收端MSDU载荷的重组，完整性校验值的计算覆盖MSDU载荷，不包括MAC帧头部。一个MAC帧只能由一个完整的MSDU生成。

载波MAC帧的生成如图24所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_222_377_992_702.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 24 载波 MAC 帧生成示意图</div>


无线MAC帧的生成如图25所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_208_805_981_1134.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 25 无线 MAC 帧生成示意图</div>


## 5253 分片

一个MAC帧由一个MSDU生成，载波上一个MAC帧可能要分多片，才能使用MPDU进行传输。PHY层在传输数据时，必须按照FEC块进行传输，FEC块支持4种大小，分别为72/136/264/520字节。所以MAC帧在交给PHY层传输前，必须适配MPDU的格式。

在对MAC帧进行分片时，参照MPDU的物理块的格式× MAC帧分片后，每一片可以作为一个“物理块体”。

分片时，可根据物理层的限制，选用合适的分片规格；并且只能用同一种规格，完成对MAC帧的分片；最后一个分片中，如果数据的大小不足时，全部以0来补充。

每一个MAC帧的分片与一个“序列号”相关联。每帧的第一个分片的“序列号”被初始化为零，一个新分片产生时进行递增。