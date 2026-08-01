<div style="text-align: center;">表 34 选择确认的可变区域</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>接收结果</td><td rowspan="2">4</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>47</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td rowspan="2">源 TEI</td><td style='text-align: center; word-wrap: break-word;'>5</td><td style='text-align: center; word-wrap: break-word;'>07</td><td rowspan="2">12</td></tr><tr><td rowspan="2">6</td><td style='text-align: center; word-wrap: break-word;'>03</td></tr><tr><td rowspan="2">目的 TEI</td><td style='text-align: center; word-wrap: break-word;'>47</td><td rowspan="2">12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>7</td><td style='text-align: center; word-wrap: break-word;'>07</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>8</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信道质量</td><td style='text-align: center; word-wrap: break-word;'>9</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点负载</td><td style='text-align: center; word-wrap: break-word;'>10</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>11</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>扩展帧类型</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

<div style="text-align: center;">表 35 接收结果值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示 SOF 帧接收成功。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>表示 SOF 帧的物理块存在循环冗余校验失败的情形。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

<div style="text-align: center;">表 36 扩展帧类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>表示为选择确认帧。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 5123 SOF 帧MPDU 帧载荷格式

载波载荷的物理块格式有4种，物理块的大小可选为72/136/264/520字节。无线载荷的物理块格式有6种，物理块的大小可选为16/40/72/136/264/520字节。

每个物理块适配到单个物理层前向纠错编码块×每个物理块包含一个物理块头×物理块体和物理块检查序列×物理块头为1个字节，物理块检查序列为3个字节×物理块的格式如图5所示×

物理块头包含物理块体的属性信息× 物理块头的格式如表37所示× 序列号是一个6比特的字段，初始值为0，表示MPDU的载荷中物理块的序号，一个MAC帧，被分割为物理块后，每个物理块需要对应一个物理块的序号，例如，如果一个MAC帧，封装在一个MPDU中，共携带了4个物理块，则第一个物理块的物理块头中，序列号的值是0；第二个物理块的物理块头中，序列号的值是1；第三个物理块的物理块头中，序列号的值是2；第四个物理块的物理块头中，序列号的值是3× 帧起始标志是一个1比特的字段，当对应的物理块体，是MAC帧分片后的第一个物理块体时，需设置本字段的值为1；否则，需设置本字段的值为0× 帧结束标志是一个1比特的字段，当对应的物理块体，是MAC帧分片后的最后一个物理块体时，需设置本字段的值为1；否则，需设置本字段的值为0×