<div style="text-align: center;">表156（续）</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>参数约束</td><td style='text-align: center; word-wrap: break-word;'>动作约定</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>心跳周期</td><td style='text-align: center; word-wrap: break-word;'>一次性周期：根据路由周期来设置。\n设置范围：2个路由周期</td><td style='text-align: center; word-wrap: break-word;'>CCO判断某个站点：在连续的1个心跳周期内，都不活跃。可判定其离线。CCO判断某个站点：在连续的4个心跳周期内，都不活跃。可判定其未入网</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线发现列表周期</td><td style='text-align: center; word-wrap: break-word;'>CCO根据本网络的规模。可设置本网络无线发现列表周期。设置范围：10 255</td><td style='text-align: center; word-wrap: break-word;'>网络中节点保证每1个无线发现列表周期发送1个无线发现列表报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线接收率老化周期</td><td style='text-align: center; word-wrap: break-word;'>CCO根据本网络的规模。可配置无线接收率老化周期。设置范围为：4 16个无线发现列表周期</td><td style='text-align: center; word-wrap: break-word;'>若超过无线接收率老化周期没有更新无线上行接收率，则老化为0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线接收统计窗口</td><td style='text-align: center; word-wrap: break-word;'>最小值为8</td><td style='text-align: center; word-wrap: break-word;'>节点本地统计接收无线发现列表接收个数位图大小</td></tr></table>

## 53413 实时路由修复

站点在转发业务数据时，如果周期性评估的路由无效或者无路由时，可根据业务报文的触发，发起实时的路由修复，以便发现到达业务报文的最终目的地址的实时路由。

当站点确认需要发起路由修复时，以广播的形式发送路由请求报文（MMeRouteRequest），对最终目的节点进行搜索。宜通过对路由请求报文的传输跳数进行限制，减小由于通信报文数量较多导致的冲突。通信延时的影响。路由请求报文传输流程如图67所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_292_884_953_1196.jpg" alt="Image" width="55%" /></div>


<div style="text-align: center;">图 67 路由修复请求报文传输流程</div>


被路由请求报文所搜索的最终站点，在接收到路由请求报文后，需要组织路由回复报文（MMeRouteReply），并将路由回复报文，以单播报文的形式发送至路由请求报文的发起站点。参与路由修复任务的站点应记录接收到的至少一条路由请求报文的信息，对于处理。转发路由回复报文的站点，应根据上述记录的信息确定发路由回复报文的下一跳站点。路由回复报文传输流程如图68所示。