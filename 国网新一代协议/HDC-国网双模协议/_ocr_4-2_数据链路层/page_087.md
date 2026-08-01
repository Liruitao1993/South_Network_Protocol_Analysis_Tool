<div style="text-align: center;"><img src="imgs/img_in_image_box_223_199_1043_369.jpg" alt="Image" width="68%" /></div>


<div style="text-align: center;">图 20 竞争帧间隔示意图 2</div>


回应帧间隔(RIFS)，一般指需要等待回应帧的场景中，在报文和报文的回应帧之间，物理层的协议帧之间需要保证的最小帧间隔。SOF帧需要等选择确认(SACK)的场景中，回应帧间隔(RIFS)如图21所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_223_507_1043_675.jpg" alt="Image" width="68%" /></div>


<div style="text-align: center;">图 21 回应帧间隔示意图</div>


扩展帧间隔(EIFS)，不是一般的连续的两个帧的帧间隔，而是对于普遍的SOF帧的竞争场景的时隙间隔的预期值，主要用来在发送报文时，设置最长的退避时间间隔x，当在退避发送时，如果检测到了报文的前导，那么缺省先需要按照扩展帧间隔的时间间隔进行退避。当“帧控制”等解析成功时，可以根据“帧控制”等的具体时隙需求退避。扩展帧间隔（EIFS）如图22所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_310_877_954_1045.jpg" alt="Image" width="54%" /></div>


<div style="text-align: center;">图 22 扩展帧间隔示意图</div>


## 52443 帧间隔的测量

在两个物理层协议帧之间的帧间隔，是通过计算在线路上最后一个OFDM的最后一个非零样本，与线路上第一个跟随帧的第一个非零样本之间的间隔时间。这种帧间隔是由传输器在发送前导时测量的，保证前导的发出时，帧间隔的测量已经完成而且足够。

实际帧间隔的测量如图23所示。其他种类的帧间隔也是按照同样的方式进行测量。