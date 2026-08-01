CSMA/CA退避算法由以下步骤组成：

a) 初始化 NB 为 0，BE 为 minBE，PE 根据报文优先级初始化，进入步骤 b)。

b) 通过公式计算退避时间: BackOffTime=(Rand(2BE 1)+PE)*SLOT TIME, 并设置 BackOffTimer, 进入步骤 c)。

c) 若 BackOffTimer 溢出前未接收到来自物理层“接收机信号接收开始状态原语”，切换物理层为发射机，启动 MPDU 帧的发送发送，进入步骤 e)，否则进入步骤 d)。

d) 若 BackOffTimer 溢出前收到来自物理层的“接收机信号接收开始状态原语”，暂停 BackOffTimer 定时器，直到报文接收结束，然后继续 BackOffTimer 运行，并进入步骤 c)。

e) 若该 MPDU 帧发送成功，则本次数据发送结束。若该 MPDU 帧发送失败，则 NB 加 1，若 NB > maxNB，则发送失败；否则，BE = min(BE++, MaxBE)，进入步骤 b)。