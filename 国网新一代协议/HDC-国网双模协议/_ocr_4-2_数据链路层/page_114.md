STA2站点的路由表项如表151所示。

<div style="text-align: center;">表 151 STA2 路由表项</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>原始目的 TEI</td><td style='text-align: center; word-wrap: break-word;'>目的 TEI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>5</td></tr></table>

在上面的几个路由表项中，当原始目的TEI与目的TEI值相等时，该条路由一般叫做直连路由；当原始目的TEI与目的TEI不等时，该条路由一般叫做间接路由。

## 5348 路由表项形成

路由的创建，主要依靠发现列表报文，关联请求报文，关联确认报文，代理变更请求报文，代理变更请求确认等报文中携带的信息进行创建。

通过发现列表报文，既可以形成直连路由表项，因为能够接收到某站点的发现列表报文，意味着该站点就可能是本站点的直接邻居；也可以形成间接路由表项，因为发现列表报文中，携带着发送发现列表报文站点的所有邻居站点，这些站点未必是本站点的邻居。

通过关联请求报文，CCO可以形成到达请求入网站点的间接路由。

通过关联确认报文，各级代理站点可以形成或者刷新到达请求入网站点的间接路由，同时，也可以形成到达请求入网站点的所有子站点的间接路由，因为关联确认报文中，“路由表信息”携带了请求入网站点的所有直连站点和直连站点的子站点。关联确认报文需要逐级代理进行转发。

通过关联确认报文，新入网站点，根据CCO告知的“路由表信息”表项，可以形成所有子站点的直连路由，以及到达直连子站点的子站点的所有间接路由。

通过代理变更请求报文，代理站点可以形成到达请求变更站点的直连路由；上级代理在处理转发代理变更请求报文的过程中，也可以形成到达请求变更站点的间接路由。同理，CCO和各级代理都能形成到达请求变更站点的间接路由。

代理变更确认报文和关联确认报文的原理一样，可以使得各级代理站点形成到达其所有子站点的路由

各级站点到达CCO的路由表项形成原理相对简单，当选定一个代理时，那么到达CCO的路由下一跳就可以缺省是代理站点，代理站点会把子站点的报文尽力的转发到CCO，通过代理站点的代理。

## 5349 载波路由机制

## 53491 载波通信率统计

载波通信率通过统计接收载波发现列表报文和载波信标帧的个数计算载波的通信率 $ x $节点为每一个邻居节点建立一个邻居节点信息表项，邻居节点载波信息表项如表152所示

<div style="text-align: center;">表 152 载波邻居节点表项字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段名称</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CurrDownRcvCnt</td><td style='text-align: center; word-wrap: break-word;'>当前路由周期下行接收发现列表和信标帧个数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>LastDownRcvCnt</td><td style='text-align: center; word-wrap: break-word;'>上一个路由周期下行接收发现列表和信标帧个数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>LastDownSndCnt</td><td style='text-align: center; word-wrap: break-word;'>上一个路由周期下行发送发现列表和信标帧个数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>LastUpRcvCnt</td><td style='text-align: center; word-wrap: break-word;'>上个路由周期上行接收发现列表和信标帧个数</td></tr></table>