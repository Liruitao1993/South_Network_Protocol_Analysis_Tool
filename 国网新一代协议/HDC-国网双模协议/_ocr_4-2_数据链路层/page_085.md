在CSMA时隙里，导致冲突的原因基本上是多个站点，退避在一个较小甚至完全重叠的时刻，进行了报文发送，导致冲突。

一般情况下，在以下a）b）两种情形中，发送端节点在发送报文后，需要等待一个回应报文，可通过以下c）d）两种情形，判断出现了冲突：

a）单播的 SOF 帧，需要接收节点回应“选择确认”报文；

b) 广播的 SOF 帧但是指定一个节点来回应“选择确认”；

c) 当报文发送完成后，在等待一个回应报文时，没有收到回应报文，或者收到一个无效的或者非预期的报文；

d) 当 SOF 帧发送后，接收到的“选择确认”帧中，提示 PHY 对全部 PB 块没有解析成功。

## 5 2 4 2 3 VCS

虚拟载波侦听（VCS），是主要用在CSMA时隙中的一种时隙预判机制，每个节点都需要支持× VCS 机制根据报文传输时间以及帧间隔确定，采用VCS定时器以及定时器到期后的信道状态实现×其中VCS定时器时长计算方法和到期后状态如表138所示×

<div style="text-align: center;">表 138 VCS 定时器时长和状态迁移</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>事件</td><td style='text-align: center; word-wrap: break-word;'>VCS 定时器时长</td><td style='text-align: center; word-wrap: break-word;'>VCS 定时器到期后信道状态</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>检测到冲突</td><td style='text-align: center; word-wrap: break-word;'>扩展帧间间隔</td><td style='text-align: center; word-wrap: break-word;'>空闲</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>检测到前导</td><td style='text-align: center; word-wrap: break-word;'>扩展帧间间隔</td><td style='text-align: center; word-wrap: break-word;'>空闲</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>解析到 SOF 的帧控制</td><td style='text-align: center; word-wrap: break-word;'>帧长*10 微秒（载波）；\n帧长*100 微秒（无线）</td><td style='text-align: center; word-wrap: break-word;'>空闲</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>解析到选择确认</td><td style='text-align: center; word-wrap: break-word;'>竞争帧间间隔</td><td style='text-align: center; word-wrap: break-word;'>空闲</td></tr></table>

## 52424 优先级

站点在CSMA时隙中，竞争信道时，需要支持优先级 $ ^{x} $。优先级高的报文，相对于优先级低的报文，应该具有更高的信道竞争能力。

## 52425 绑定 CSMA

绑定CSMA是指一段CSMA时隙，可以分配给某个优先级的业务或者某个种类的业务报文的传输。在该时隙内，只能传输所分配的优先级或者种类的业务报文。

各个节点在绑定CSMA时隙中，需要按照一般的CSMA机制，进行信道竞争，竞争成功后，才能发送对应优先级或者种类的业务报文。

## 52426 多相线 CSMA

多相线CSMA是指分配给不同相线的电力线上站点使用的时隙×STA需要和CCO进行通信时，要按照多相线的时隙规划使用多相线时隙×不同相线的STA，只能在对应相线的时隙里，才能向CCO发送报文×

多相线CSMA时隙，是由同一相线下的所有STA竞争使用的。

## 52427 CSMA 退避机制

BE（Backoff Exponent）退避指数，SLOT TIME指退避时间单位。CSMA退避机制参数如表139所示。