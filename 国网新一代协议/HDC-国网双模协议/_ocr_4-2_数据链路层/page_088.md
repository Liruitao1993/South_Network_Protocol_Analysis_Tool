<div style="text-align: center;"><img src="imgs/img_in_image_box_178_199_1037_391.jpg" alt="Image" width="72%" /></div>


<div style="text-align: center;">图 23 帧间隔测量示意图</div>


## 52444 帧间隔范围

载波帧间隔取值范围定义如表140所示。

<div style="text-align: center;">表 140 载波帧间隔取值范围</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>取值范围</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>竞争帧间隔 CIFS</td><td style='text-align: center; word-wrap: break-word;'>400 微秒</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>突发帧间隔 BIFS</td><td style='text-align: center; word-wrap: break-word;'>400 微秒</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>回应帧间隔 RIFS</td><td style='text-align: center; word-wrap: break-word;'>400~2300 微秒</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>扩展帧间隔 EIFS</td><td style='text-align: center; word-wrap: break-word;'>20 毫秒</td></tr></table>

无线帧间隔取值范围定义如表141所示。

<div style="text-align: center;">表 141 无线帧间隔取值范围</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>取值范围</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>竞争帧间隔 CIFS</td><td style='text-align: center; word-wrap: break-word;'>800 微秒</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>突发帧间隔 BIFS</td><td style='text-align: center; word-wrap: break-word;'>800 微秒</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>回应帧间隔 RIFS</td><td style='text-align: center; word-wrap: break-word;'>800~2300 微秒</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>扩展帧间隔 EIFS</td><td style='text-align: center; word-wrap: break-word;'>70 毫秒</td></tr></table>

## 525 数据处理

## 5251 数据处理过程

MAC层处理的基本业务数据单元称作MSDU

MAC层处理MSDU时，先将MSDU封装生成MAC帧×MAC帧是不同站点的MAC层之间进行数据传送的基本传输单元×

MAC层根据MAC帧头中的“原始源MAC地址”和“原始目的MAC地址”字段，来区分MSDU的原始源地址和原始目的地址，并且在高速载波和无线双模通信网络中传输时，使用“原始源TEI”和“原始目的TEI”与之相对应。

## 5252 MAC 帧生成