<div style="text-align: center;">表14 定界符类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>信标帧</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>SOF 帧</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>选择确认帧</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>网间协调帧</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51223 网络类型

网络类型是一个的5比特的字段，用于指示发送MPDU站点所在的网络类型。网络类型字段的取值和所代表的含义如表15所示。

<div style="text-align: center;">表 15 网络类型</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>MPDU 在用电信息采集系统中传输</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

## 51224 网络标识

网络标识是一个24比特的字段，用于区分不同的高速载波通信网络。有效取值范围为1 16777215。每个高速载波通信网络都必须有一个唯一的NID。

## 51225 标准版本号

标准版本号是一个4比特字段，用来表示标准演进的不同版本。标准版本号用以识别发送报文站点或者网络所使用的标准版本。其含义如表16所示。

<div style="text-align: center;">表16 标准版本号</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>本标准</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他</td><td style='text-align: center; word-wrap: break-word;'>待演进</td></tr></table>

## 51226 帧控制校验序列

帧控制校验序列为帧控制的末尾24比特，校验计算帧控制中除帧控制校验序列以外的字段。帧控制校验序列采用的是24比特的循环冗余校验算法。

## 51227 载波可变区域

可变区域的内容由定界符类型决定。

信标帧用于CCO进行网络管理。信标帧的可变区域的格式如表17所示。信标时间戳是发送信标的设备在发送信标时标记的网络基准时间，网络基准时间由CCO维护，全网站点需要和CCO的网络基准时间保持同步，在中央信标中，信标时间戳是网络基准时间，在代理信标中，信标时间戳是由PCO评估