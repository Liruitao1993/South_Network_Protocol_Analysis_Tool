d) STA 站点接收到离线指示报文，指示自己离线；

e) 一级 STA 站点，如果检测到 CCO 的 MAC 地址发生变化，且已经连续一个周期；

f) STA 站点发现本站点的代理站点角色变为了发现站点已经连续一个路由周期；

g）本站点的层级超过最大层级限制（15级），站点需要离线。

## 5347 路由表维护

在组网过程中以及网络维护的过程中，全网站点最关键的目标就是维护实时的路由表项，路由表项包括STA站点到达CCO的路由，也包括从CCO或者低层级站点到达最大层级的STA站点的路由。

当各级站点中的路由表项是实时可靠时，才能有效的支撑业务数据的转发。

网络拓扑图示例如图47所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_529_534_715_908.jpg" alt="Image" width="15%" /></div>


<div style="text-align: center;">图 47 网络拓扑图</div>


CCO站点的路由表项如表149所示。

<div style="text-align: center;">表 149 CCO 路由表项</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>原始目的 TEI</td><td style='text-align: center; word-wrap: break-word;'>目的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

STA1站点的路由表项如表150所示。

<div style="text-align: center;">表 150 STA1 路由表项</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>原始目的 TEI</td><td style='text-align: center; word-wrap: break-word;'>目的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>