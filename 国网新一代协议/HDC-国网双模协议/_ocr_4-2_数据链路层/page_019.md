<div style="text-align: center;"><img src="imgs/img_in_image_box_250_200_1014_355.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 6 带选择确认的单帧传输</div>


<div style="text-align: center;">表21 广播标志位</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>非广播报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>广播报文</td></tr></table>

<div style="text-align: center;">表22 重传标志位</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>非重传报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>重传报文</td></tr></table>

选择确认帧是接收设备用来向发送设备反馈SOF帧的接收情况×接收SOF帧的设备，如果判断需要回复选择确认帧时，则发送选择确认帧，选择确认帧的可变区域内容表23所示，接收结果，表示SOF帧的接收结果，接收结果的取值和解释如表24所示，接收状态，接收状态是一个4比特的字段，用来表示普通模式时，SOF帧的物理块的校验结果×一个SOF帧最多可以携带4个物理块，每一个比特，表示一个物理块是否校验成功，比特0表示序列号为0的物理块的校验结果，比特1表示序列号为1的物理块的校验结果，其余类推，接收状态的比特位为0时，则表示对应的物理块校验失败，比特位为1时，则表示对应的物理块校验成功，源TEI是一个12比特字段，表示为选择确认帧的源终端的TEI×目的TEI是一个12比特字段，表示为选择确认帧的目的终端的TEI×接收物理块个数，接收的物理块个数，包括解析错误的物理块个数×信道质量，表示站点在接收本帧所对应的SOF报文时，计算得到的信道质量×信道质量用原始信噪比数据表示×站点负载，表示选择确认帧的源站点的负载，取值为该源站点上未发送的缓存报文的数量×扩展帧类型，表示在定界符类型之上，所扩展定义的帧类型，含义如表25所示×

<div style="text-align: center;">表23 选择确认的可变区域</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收结果</td><td rowspan="2">4</td><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收状态</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td rowspan="2">源 TEI</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">12</td></tr><tr><td rowspan="2">6</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td rowspan="2">目的 TEI</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td rowspan="2">12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>0 7</td></tr></table>