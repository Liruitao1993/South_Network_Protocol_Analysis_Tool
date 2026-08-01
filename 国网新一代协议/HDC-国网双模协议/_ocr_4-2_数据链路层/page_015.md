<div style="text-align: center;"><img src="imgs/img_in_image_box_175_209_1039_401.jpg" alt="Image" width="72%" /></div>


<div style="text-align: center;">图 3 载波 MPDU 帧格式</div>


无线信道上仅支持1个物理块载荷的MPDU。无线MPDU帧格式如图4所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_179_513_1040_708.jpg" alt="Image" width="72%" /></div>


<div style="text-align: center;">图 4 无线 MPDU 帧格式</div>


## 5122 MPDU 帧控制格式

## 51221 MPDU 帧控制格式定义

MPDU的帧控制字段长度为16字节。MPDU帧控制字段的格式如表13所示。

<div style="text-align: center;">表 13 MPDU 帧控制字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>字段大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>定界符类型</td><td rowspan="2">0</td><td style='text-align: center; word-wrap: break-word;'>0 2</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络类型</td><td style='text-align: center; word-wrap: break-word;'>3 7</td><td style='text-align: center; word-wrap: break-word;'>5</td></tr><tr><td rowspan="3">网络标识</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="3">24</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>0 7</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0 7</td></tr><tr><td rowspan="2">可变区域</td><td style='text-align: center; word-wrap: break-word;'>4 11</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td rowspan="2">68</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>0 3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>标准版本号</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>4 7</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>帧控制校验序列</td><td style='text-align: center; word-wrap: break-word;'>13 15</td><td style='text-align: center; word-wrap: break-word;'>0 7</td><td style='text-align: center; word-wrap: break-word;'>24</td></tr></table>

## 51222 定界符类型

定界符类型长度为3比特，用来指示MPDU的帧类型。MPDU帧类型的不同，可变区域也不同。定界符类型的取值如表14所示。