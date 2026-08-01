<div style="text-align: center;">表 139 CSMA/CA 退避参数</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>参数名称</td><td style='text-align: center; word-wrap: break-word;'>意义</td><td style='text-align: center; word-wrap: break-word;'>取值</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>minBE</td><td style='text-align: center; word-wrap: break-word;'>最小退避指数</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>maxBE</td><td style='text-align: center; word-wrap: break-word;'>最大退避指数</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>BE</td><td style='text-align: center; word-wrap: break-word;'>退避指数</td><td style='text-align: center; word-wrap: break-word;'>minBE→maxBE</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>SLOT TIME</td><td style='text-align: center; word-wrap: break-word;'>退避时间单位</td><td style='text-align: center; word-wrap: break-word;'>根据优先级从低到高0-3（0为低优先级），依次取值为10，8，6，4个OFDM符号。</td></tr></table>

## 5 2 4 3 TDMA 信道访问

TDMA是指由CCO分配给指定节点的TDMA时隙。

在该时隙内，节点不需要进行信道竞争，可以独占被分配的TDMA时隙，进行报文的发送。

TMDA时隙一般分配给某个优先级的业务或者某个种类的业务，该时隙内只能传输对应的业务报文。

## 5244 帧间隔

## 52441 帧间隔定义

帧间隔是指线路上传输的物理层协议帧之间需要保证的最少时间间隔。

## 52442 帧间隔类型

突发帧间隔（BIFS），一般指在不需要竞争的时隙中，连续发送报文时，物理层的协议帧之间需要保证的最小帧间隔。主要的应用场景有信标的连续发送等。信标发送场景中，突发帧间隔（BIFS）如图18所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_225_1005_1040_1118.jpg" alt="Image" width="68%" /></div>


<div style="text-align: center;">图 18 突发帧间隔示意图</div>


竞争帧间隔（CIFS），一般指在需要竞争的时隙中，当站点需要发送报文时，物理层的协议帧之间需要保证的最小帧间隔。SOF帧不等选择确认(SACK)的场景中，竞争帧间隔（CIFS）如图19所示。SOF帧需要等选择确认(SACK)的场景中，竞争帧间隔(CIFS)如图20所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_224_1317_1041_1484.jpg" alt="Image" width="68%" /></div>


<div style="text-align: center;">图 19 竞争帧间隔示意图 1</div>
