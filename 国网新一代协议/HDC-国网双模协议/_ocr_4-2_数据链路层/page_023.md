<div style="text-align: center;">表31 链路标识符定义</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0 3</td><td style='text-align: center; word-wrap: break-word;'>报文优先级</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4 254</td><td style='text-align: center; word-wrap: break-word;'>业务分类 LID</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>255</td><td style='text-align: center; word-wrap: break-word;'>无效值</td></tr><tr><td colspan="2">注：链路标识符越大，优先级越高。</td></tr></table>

<div style="text-align: center;"><img src="imgs/img_in_image_box_248_441_1013_595.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图7 无选择确认的单帧传输</div>


<div style="text-align: center;"><img src="imgs/img_in_image_box_249_670_1014_828.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 8 带选择确认的单帧传输</div>


<div style="text-align: center;">表 32 广播标志位</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>非广播报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>广播报文</td></tr></table>

<div style="text-align: center;">表 33 重传标志位</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>非重传报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>重传报文</td></tr></table>

选择确认帧是接收设备用来向发送设备反馈SOF帧的接收情况×接收SOF帧的设备，如果判断需要回复选择确认帧时，则发送选择确认帧×选择确认帧的可变区域内容表34所示×接收结果，表示SOF帧的接收结果，接收结果的取值和解释如表35所示×源TEI是一个12比特字段，表示为选择确认帧的源终端的TEI×目的TEI是一个12比特字段，表示为选择确认帧的目的终端的TEI×信道质量，表示站点在接收本帧所对应的SOF报文时，计算得到的信号强度×站点负载，表示选择确认帧的源站点的负载，取值为该源站点上未发送的缓存报文的数量×扩展帧类型，表示在定界符类型之上，所扩展定义的帧类型，含义如表36所示×