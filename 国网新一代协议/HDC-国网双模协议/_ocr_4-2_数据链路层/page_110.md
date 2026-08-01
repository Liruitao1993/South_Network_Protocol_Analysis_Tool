<div style="text-align: center;">表 147 示例 6 信标时隙条目值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>TEI</td><td style='text-align: center; word-wrap: break-word;'>信标类型</td><td style='text-align: center; word-wrap: break-word;'>无线信标标志</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

示例7：CCO使用6个CCO信标时隙和1个非CCO信标时隙在无线信道上发送1个标准信标帧。网络拓扑和时隙排布如图46所示，信标时隙条目如表148所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_145_577_1064_796.jpg" alt="Image" width="77%" /></div>


<div style="text-align: center;">图 46 示例 7 时隙调度示意图</div>


<div style="text-align: center;">表 148 示例 7 信标时隙条目值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>TEI</td><td style='text-align: center; word-wrap: break-word;'>信标类型</td><td style='text-align: center; word-wrap: break-word;'>无线信标标志</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

## 5342 高速载波发现列表报文

大规模的高速载波通信网络中，每个入网的站点，包括CCO，都存在载波的邻居站点，邻居站点或者是CCO，或者是代理站点，或者是其他的STA站点。某个站点的邻居站点，即是与该站点能够进行载波通信的站点。

组网过程中，每个站点可以根据接收的载波发现信标，感知自己的邻居站点，并记录下来，形成一个发现列表。站点的中继路由，就可以在自己的发现列表中进行选择。

如果每个站点将本站点的发现列表广播发布，则有利于形成更全面的网络拓扑信息，有利于站点寻找更合适的路由。发现列表报文主要用于路由评估，发现列表报文的发送周期，需要根据路由周期确定。路由周期，根据网络规模的增大，可在20 420秒内，逐渐增大，一个路由周期中，必须至少发送10次发现列表。