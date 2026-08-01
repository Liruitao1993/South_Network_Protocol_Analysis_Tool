VCS: 虚拟载波侦听（Virtual Carrier Sensing）

VF: 可变区域（Variant Field）

VLAN: 虚拟局域网（Virtual Local Area Network）

## 5 数据链路层

## 51 帧格式

## 511 MAC 帧格式

## 5 1 1 1 MAC 帧格式定义

MAC帧是不同站点的MAC层之间进行数据传送的基本传输单元 $ ^{x} $。一个MAC帧由MAC帧头，MAC业务数据单元和完整性校验值组成。载波MAC帧的基本格式如图1所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_175_632_1038_827.jpg" alt="Image" width="72%" /></div>


<div style="text-align: center;">图 1 载波 MAC 帧格式</div>


无线MAC帧的基本格式如图2所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_178_941_1038_1136.jpg" alt="Image" width="72%" /></div>


<div style="text-align: center;">图 2 无线 MAC 帧格式</div>


## 5 1 1 2 MAC 帧头固定域格式

MAC帧头固定格式如表1所示。

<div style="text-align: center;">表1 MAC 帧头固定域字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小(比特)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>可变区域</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>可变长</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

版本是一个4比特的字段。该字段用来指示MAC帧头的字段定义版本号。版本字段的含义如表2所示。