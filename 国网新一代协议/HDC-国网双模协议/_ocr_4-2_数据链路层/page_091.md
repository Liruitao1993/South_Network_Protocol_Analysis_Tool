<div style="text-align: center;"><img src="imgs/img_in_image_box_207_193_1009_829.jpg" alt="Image" width="67%" /></div>


<div style="text-align: center;">图 27 短 MPDU 生成示意图</div>


## 5255 重组

当一个MAC帧的分片后的“物理块体”，被接收方接收成功后，则需要将该MAC帧所有的“物理块体”重组成为一个MAC帧。

重组时，需要根据“物理块头”中的“序列号”，“帧起始标志”，“帧结束标志”，将所有的“物理块体”进行有序的重组。重组的分片，可以是来自于同一个MPDU中的“物理块体”，也可以是来自连续的多个MPDU中的“物理块体”。

重组完成后，需要进行完整性校验，以判断MAC帧的传输完整。一个重组后的MAC帧只能提取一个完整的MSDU。

MAC帧重组的过程，正好和MAC帧分片的过程相反，如图28所示。