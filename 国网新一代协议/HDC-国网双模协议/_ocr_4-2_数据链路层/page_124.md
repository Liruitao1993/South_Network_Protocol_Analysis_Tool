在网络组网的过程中，站点可以通过判断接收信标帧的情况，来判断周围站点的信道质量；在组网完成后，网络中主要的维护报文就是发现列表报文和信标帧，各级站点可以通过判断接收邻居站点的发现列表报文和信标帧的情况，以及邻居站点的变化情况选择更好的代理。

当STA站点评估出一个新的代理站点时，可以通过代理变更请求报文，向CCO发起代理变更请求。CCO根据网络拓扑的组成，可以在STA站点申请的备选代理中指定一个站点，作为STA站点的新代理。当CCO判断变更后的网络拓扑层级会超过层级上限（最大支持15个层级）时，不会响应代理变更请求，并且不会发送代理变更请求确认报文。

当一个新代理PCO被确认后，CCO需要发送代理变更确认报文等，将STA站点以及新代理PCO的情况，通过逐级代理转发给请求代理变更的站点。逐级代理在转发代理变更确认等报文的过程中，可以通过该报文中的“子站点条目”等信息（见第5.1.3.6.1节），实时的刷新到达“子站点条目”中站点的间接路由。STA站点最终也可以根据“子站点条目”信息，刷新本地的直接路由和间接路由。

所以，在组网完成后，网络维护的过程中，全网站点的路由表项，主要通过代理变更的过程来完成实时刷新 $ ^{*} $

## 53412 周期参数

在整个网络维护的机制中，存在一些周期性的参数设计，具体内容整理如表156所示。

<div style="text-align: center;">表 156 周期参数</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>名称</td><td style='text-align: center; word-wrap: break-word;'>参数约束</td><td style='text-align: center; word-wrap: break-word;'>动作约定</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络监听周期</td><td style='text-align: center; word-wrap: break-word;'>一次性周期，设置范围：小于10秒</td><td style='text-align: center; word-wrap: break-word;'>CCO上电后，在该周期内，监听邻居网络的网间协调帧，进行网络标识的协商</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网间协调报文发送周期</td><td style='text-align: center; word-wrap: break-word;'>连续性周期，设置范围：小于1秒</td><td style='text-align: center; word-wrap: break-word;'>CCO确定网络标识，开始组网后，在网络维护期间，需要每个周期内发送1个网间协调帧</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信标周期</td><td style='text-align: center; word-wrap: break-word;'>连续性周期，CCO根据本网络的规模，可设置本网络的信标周期，设置范围：1 15秒</td><td style='text-align: center; word-wrap: break-word;'>CCO在每个信标周期中，须要发送中央信标；每个代理站点在每个信标周期中，都要发送代理信标，发送时间根据中央信标的安排；每个信标周期中，部分STA站点会被CCO安排发送发现信标</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>载波路由周期</td><td style='text-align: center; word-wrap: break-word;'>连续性周期，CCO根据本网络的规模，可设置本网络的路由周期，设置范围：20 420秒</td><td style='text-align: center; word-wrap: break-word;'>STA站点，在路由周期内，评估自己的代理站点，可发起代理变更请求</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>载波发现列表报文发送周期</td><td style='text-align: center; word-wrap: break-word;'>连续性周期，根据路由周期来设置，设置范围：1个路由周期</td><td style='text-align: center; word-wrap: break-word;'>网络中所有站点，在该周期内，至少发送10个发现列表报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>心跳检测报文产生周期</td><td style='text-align: center; word-wrap: break-word;'>连续性周期，根据路由周期来设置，设置范围：1/8个路由周期</td><td style='text-align: center; word-wrap: break-word;'>高层级代理站点，在该周期内，产生1个心跳检测报文</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信成功率上报周期</td><td style='text-align: center; word-wrap: break-word;'>连续性周期，根据路由周期来设置，设置范围：4个路由周期</td><td style='text-align: center; word-wrap: break-word;'>代理站点，在该周期内，需要产生1个通信成功率上报报文，发送给CCO</td></tr></table>