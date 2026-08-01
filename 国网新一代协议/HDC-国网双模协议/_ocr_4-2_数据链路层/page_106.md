规则1：无线信标帧优先复用高速载波信标时隙×即在同一个时隙上，存在一个节点在高速载波上发送信标，一个节点在无线上发送信标。

规则2：发现节点在无线信道上发送无线精简信标帧。

规则3：代理节点的直连子节点都可以通过高速载波通信，则该代理节点在无线上发送无线精简信标帧×

规则4：节点A为节点B的代理，节点A和B之间仅能通过无线进行通信，并且在一个信标周期内，安排节点B在高速载波上发送信标帧x，则在排布A和B的时隙时，尽量在A和B之间安排多个仅需要在CSMA时隙发送无线精简信标的时隙，A和B之间的时隙组成一个在无线信道上发送标准信标帧的时隙，从而满足规则1。

规则5：节点A为节点B的代理，节点A和B之间仅能通过无线进行通信，并且在一个信标周期内，安排节点B在高速载波上发送信标帧 $ _{x} $。若排布A和B的时隙时，无法满足规则4，则可以在A和B之间安排多个仅在无线上发送标准信标的时隙，用来满足节点A在无线上发送标准信标 $ _{x} $。

规则6：CCO存在直连无线子节点，并且在一个信标周期内安排其直连无线子节点形成的子树上节点发送信标帧，则CCO需要在无线上发送标准信标帧，其他情况，CCO发送精简信标。

规则7：无线上不分相线，CCO只需要发送一个无线信标帧。

规则8：若3个CCO时隙和1个非CCO时隙满足在无线信道上发送标准信标，则直接复用3个CCO时隙在无线信道上发送标准信标。若无法满足无线信道上一个标准信标帧的时长，存在可以复用的非CCO时隙，则复用3个CCO时隙和多个非CCO时隙，组成一个在无线信道上发送标准信标帧的时隙。若没有可复用的非CCO时隙，则给CCO安排多个时隙（最多可安排15个），用来组成一个在无线信道上发送标准信标帧的时隙。

规则9：无特殊要求，比如为了满足上述规则4或者8，信标时隙排布按网络的层级，先按照低层级的代理站点发送信标帧，然后再安排高层级的节点发送信标帧。

## 53413 时隙调度示例

示例1：无线信标帧帧长小于一个信标时隙长度，同一个节点无线信标和载波信标错位发送。网络拓扑和信标时隙排布如图40所示，信标条目如表142所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_144_1007_1063_1260.jpg" alt="Image" width="77%" /></div>


<div style="text-align: center;">图 40 示例 1 时隙调度示意图</div>


<div style="text-align: center;">表 142 示例 1 信标条目值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>TEI</td><td style='text-align: center; word-wrap: break-word;'>信标类型</td><td style='text-align: center; word-wrap: break-word;'>无线信标标志</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr></table>