<div style="text-align: center;">表 64 MAC 地址类型字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>电能表地址作为入网 MAC 地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>通信模块本身的 MAC 地址作为入网 MAC 地址</td></tr></table>

## 51328 模块类型

表示发送关联请求站点通信模块的类型，定义如表65所示。

<div style="text-align: center;">表65 模块类型值</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>高速载波单模模块</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>双模高速载波和无线模块</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>无线单模模块</td></tr></table>

## 51329 站点关联随机数

表示模块关联入网的随机数，设备出厂后，初次上电时会自动获取一个32比特的随机值作为关联随机数，后续掉电后再上电，不再重新获取。

## 513210 厂家自定义信息

表示厂家可随关联请求附带的自定义信息，根据实际需要使用。

## 513211 站点版本信息

版本信息定义如表66所示。

<div style="text-align: center;">表66 版本信息字</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>字段大小（字节）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>系统启动原因</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>BOOT 版本号</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>软件版本号</td><td style='text-align: center; word-wrap: break-word;'>2 3</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本时间</td><td style='text-align: center; word-wrap: break-word;'>4 5</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>厂商代码</td><td style='text-align: center; word-wrap: break-word;'>6 7</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>芯片代码</td><td style='text-align: center; word-wrap: break-word;'>8 9</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

系统启动的原因，定义如表67所示。

<div style="text-align: center;">表67 系统启动原因字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0</td><td style='text-align: center; word-wrap: break-word;'>正常启动</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x1</td><td style='text-align: center; word-wrap: break-word;'>断电重启</td></tr></table>