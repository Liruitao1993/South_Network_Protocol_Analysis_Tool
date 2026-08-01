<div style="text-align: center;"><img src="imgs/img_in_image_box_292_198_954_551.jpg" alt="Image" width="55%" /></div>


<div style="text-align: center;">图 68 路由修复回复报文传输流程</div>


发起路由请求的站点在预定时间内收到了相应的路由回复报文，则该站点将向被搜索的最终目的站点发送路由应答报文（MMeRouteAck），通知该最终目的节点。路由应答过程如图69所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_289_699_957_1026.jpg" alt="Image" width="56%" /></div>


<div style="text-align: center;">图 69 路由修复路由回应报文</div>


发起路由请求报文的站点，如果在预定时间内未收到相应的路由回复报文，该站点将向触发本次路由请求任务的原始站点发送路由错误报文（MMeRouteError），以单播报文的形式通知任务的原始站点业务报文转发失败。

站点在转发路由回复报文时，可以使用链路确认请求报文（MMeLinkConfirmRequest），发起链路评估，以便确定路由回复报文的下一个目的站点。

站点在收到链路确认请求报文后，在评估本地的相关路由数据后，确定是否发送链路确认回应报文（MMeLinkConfirmResponse）。通过链路回应报文，携带相关的链路信息，回应给链路确认报文的发起站点。链路确认过程如图70所示。