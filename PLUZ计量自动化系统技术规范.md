<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//fc5068cb-c06a-4d5a-a5b3-3637c6db9dae/markdown_0/imgs/img_in_image_box_796_177_1044_278.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A44Z%2F-1%2F%2F40c08313ef9a85897612e058a271c9d2ce5d613359324b306bbe143129719b55" alt="Image" width="15%" /></div>


# xxxxx有限责任公司企业标准

X/XXX XXXXXX-2025

# DLMS计量自动化系统技术规范 第4-1部分：集中器本地通信模块接口 协议

2025-XX-XX发布

2025-XX-XX 实施

xxxx有限责任公司 发布

## 目 次

前言.....Ⅱ    
1 范围.....1    
2 规范性引用文件.....1    
3 术语和定义.....1    
4 符号和缩略语.....2    
5 帧结构.....2    
6 用户数据结构.....4    
附录 A 集中器与本地通信模块交互流程.....49

## 前言

按照xxxx有限责任公司实现电能计量“标准化、电子化、自动化、智能化”的战略目标要求，参考IEC国际标准，结合公司拓展海外营销计量业务需求，起草xxxx有限责任公司海外计量自动化系统技术规范。该系列技术规范分为下列部分：

——X-XXXXXX-2025 PLUZ计量自动化系统技术规范 第1部分 总则

——X-XXXXXXX-2025 PLUZ计量自动化系统技术规范 第2部分：信息交换安全认证

——X-XXXXXX-2025 PLUZ计量自动化系统技术规范 第3-1部分：集中器上行通信规约

——X-XXXXXXX-2025 PLUZ计量自动化系统技术规范 第3-2部分：电能表通信规约

——X-XXXXXX-2025 PLUZ计量自动化系统技术规范 第3-3部分：集中器对象清单

——X-XXXXXXX-2025 PLUZ计量自动化系统技术规范 第3-4部分：电能表对象清单

——X-XXXXXX-2025 PLUZ计量自动化系统技术规范 第4-1部分：集中器本地通信模块接口协议

——X-XXXXXX-2025 PLUZ计量自动化系统技术规范 第4-2部分：电能表本地通信模块接口协议

——X-XXXXXXX-2025 PLUZ计量自动化系统技术规范 低压电力线宽带载波通信规约 低压电力线宽带

载波通信规约 第5部分：应用层通信协议

本文件是海外计量自动化系统技术规范 集中器本地通信模块接口协议。

本文件对海外计量自动化系统中终端和本地通信模块之间的通讯协议进行了详细描述，是xxxx有限责任公司拓展海外计量自动化系统的技术依据。

请注意本文件的某些内容可能涉及专利，本文件的发布机构不承担识别专利的责任。

本文件由xxxx有限责任公司标准化部提出、归口管理。

本文件主编单位：XX

本文件主要起草人：XX

本文件由xxxx有限责任公司市场营销部负责解释。

本文件在执行过程中的意见或建议反馈至xxxx有限责任公司标准化部

# PLUZ 计量自动化系统技术规范 第 2–2 部分：集中器本地通信模块接口协议

## 1 范围

本标准规定了PLUZ计量自动化系统技中集中器和本地通信模块之间进行数据传输的帧格式、数据编码及传输规则。规定了集中器和本地通信模块的交互流程。

本标准适用于PLUZ计量自动化系统中基于低压电力线载波、双模、传输通道的本地通信模式，适用于集中器与本地通信模块之间的数据交换。

## 2 规范性引用文件

下列文件中的条款通过本部分的引用而成为本部分的条款。凡是注日期的引用文件，其随后所有的修改单（不包括勘误的内容）或修订版均不适用于本部分，然而，鼓励根据本部分达成协议的各方研究是否可使用这些文件的最新版本。凡是不注日期的引用文件，其最新版本适用于本部分。

IEC 60870-5-1:1990 elecontrol equipment and systems; part 5: transmission protocols; section one: transmission frame formats

IEC 60870-5-2:1992 Telecontrol equipment and systems; part 5: transmission protocols; section 2: link transmission procedures

IEC 60870-5-3:1992 Telecontrol equipment and systems; part 5: transmission protocols; section 3: general structure of application data

IEC62056-62: Electricity metering - Data exchange for meter reading, tariff and load control - Part 62: Interface classes

## 3 术语和定义

以下术语和定义适用于本标准：

### 3.1 主节点 primary node

集中器所在的本地通信模块。

### 3.2 从节点 secondary node

计量点（电能表）所在的本地通信模块。

### 3.3 源地址 source address

传输数据帧的起始发送方的节点MAC地址。

### 3.4 目的地址 destination address

传输数据帧的最终接收方的节点MAC地址。

### 3.5 节点 MAC 地址 node MAC address

节点 MAC 地址为本地通信网络中节点之间交互报文的通信地址。主节点通信地址为集中器逻辑地址；从节点通信地址为电能表地址或者由集中器指定。

本标准的地址均为BIN格式，当集中器、电能表的地址为BCD格式时，按以下示例进行转换。

例：若电能表地址为BCD格式的12 34 56 78 90 12，则BIN格式为0x12 0x34 0x56 0x78 0x90 0x12；若集中器的地址为44 01 02 01 0A 0C，则BIN格式为0x44 0x01 0x02 0x01 0x0A 0x0C。

## 4 符号和缩略语

本部分中所使用到的符号和缩略语见。

<div style="text-align: center;"><div style="text-align: center;">表 1 缩略语</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>符号和缩略语</td><td style='text-align: center; word-wrap: break-word;'>表示</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>A</td><td style='text-align: center; word-wrap: break-word;'>地址域</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ASRC</td><td style='text-align: center; word-wrap: break-word;'>源地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ADST</td><td style='text-align: center; word-wrap: break-word;'>目的地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>AFN</td><td style='text-align: center; word-wrap: break-word;'>应用功能码</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>二一十进制编码</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>二进制编码</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>BS</td><td style='text-align: center; word-wrap: break-word;'>独立位组合</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>C</td><td style='text-align: center; word-wrap: break-word;'>控制域</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>SEQ</td><td style='text-align: center; word-wrap: break-word;'>帧序列域</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CS</td><td style='text-align: center; word-wrap: break-word;'>帧校验和</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DIR</td><td style='text-align: center; word-wrap: break-word;'>传输方向位</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>PRM</td><td style='text-align: center; word-wrap: break-word;'>启动标志位</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>ADD</td><td style='text-align: center; word-wrap: break-word;'>地址域标识</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI</td><td style='text-align: center; word-wrap: break-word;'>数据标识编码</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>L</td><td style='text-align: center; word-wrap: break-word;'>长度</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>L1</td><td style='text-align: center; word-wrap: break-word;'>用户数据长度</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DLMS</td><td style='text-align: center; word-wrap: break-word;'>设备语言报文规范</td></tr></table>

## 5 帧结构

### 5.1 参考模型

基于 IEC 60870-5-3:1992 规定的三层参考模型 “增强性能体系结构”。

### 5.2 字节格式

帧的基本单元为8位字节。链路层传输顺序为低位在前，高位在后；低字节在前，高字节在后。

字节传输按异步方式进行，通信速率默认为115200bps，模块可支持多种速率可配置。集中器通过波特率自适应匹配模块通信速率。基本单元包含1个起始位“0”、8个数据位、1个停止位“1”，偶校验。定义见下图。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>D0</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>P</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>起始位</td><td colspan="8">8 个数据位</td><td style='text-align: center; word-wrap: break-word;'>偶校验位</td><td style='text-align: center; word-wrap: break-word;'>停止位</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">图 1 传输字节格式</div> </div>


### 5.3 帧格式

#### 5.3.1 帧格式定义

本部分采用 IEC 60870-5-1:1990 的异步式传输帧格式，定义见下图。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>起始字符（68H）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>长度 L</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>控制域 C</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>用户数据</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>校验和 CS</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>结束字符（16H）</td></tr></table>





<div style="text-align: center;"><div style="text-align: center;">图 2 传输帧格式</div> </div>


b) 帧的字符之间无线路空闲间隔。

c) 如按 d）检出了差错，两帧之间的线路空闲间隔最少需 33 位。

删除[狼 3]:

1）对于每个字符：校验起始位、停止位、偶校验位。

2) 对于每帧：

(1) 检验帧的起始字符；

(2) 识别长度 L;

(3) 每帧接收的字符数为用户数据长度 L1+6;

删除[狼 3]:

(4) 帧校验和；

(5) 结束字符；

(6) 校验出一个差错时，需符合 c）的线路空闲间隔要求。

若这些校验有一个失败，舍弃此帧；若无差错，则此帧数据有效。

#### 5.3.2 长度 L

长度L是指帧数据的总长度，由2字节组成，BIN格式，包括用户数据长度L1和6个字节的固定长度（起始字符、长度、控制域、校验和、结束字符）。

#### 5.3.3 控制域 C

控制域C表示报文的传输方向、启动标志和通信模块的通信方式类型信息，由1字节组成，定义见下图。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//a4d92c9d-a2ea-40b6-a21b-dcbab2107676/markdown_1/imgs/img_in_image_box_296_1081_925_1195.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A34Z%2F-1%2F%2F24e1ae94ab4317828aec0301acf8726625dfdb175ec7ccb0ff655558cc6cb588" alt="Image" width="39%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 3 控制域定义</div> </div>


#### 5.3.4 传输方向位 DIR

DIR=0: 表示此帧报文是由集中器发出的下行报文；DIR=1: 表示此帧报文是由通信模块发出的上行报文。

PRM=1：表示此帧报文来自启动站；PRM=0：表示此帧报文来自从动站。

#### 5.3.5 启动标志位 PRM

#### 5.3.6 地址域标识 ADD

ADD=1：表示此帧报文带地址域；ADD=0：表示此帧报文不带地址域。

#### 5.3.7 协议版本号 VER

本协议版本号为1。

#### 5.3.8 用户数据

具体定义参见第5章“用户数据结构”。

删除[狼 3]:

#### 5.3.9 帧校验和

帧校验和是控制域和用户数据区所有字节的八位位组算术和，不考虑溢出位。

### 5.4 链路传输

#### 5.4.1 传输服务类别

传输服务类别见下表。

<div style="text-align: center;"><div style="text-align: center;">表 2 传输服务类别</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>类别</td><td style='text-align: center; word-wrap: break-word;'>功能</td><td style='text-align: center; word-wrap: break-word;'>用途</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>S1</td><td style='text-align: center; word-wrap: break-word;'>发送/无回答</td><td style='text-align: center; word-wrap: break-word;'>启动站发送传输，从动站不回答。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>S2</td><td style='text-align: center; word-wrap: break-word;'>发送/确认</td><td style='text-align: center; word-wrap: break-word;'>启动站发送命令，从动站回答确认/否认。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>S3</td><td style='text-align: center; word-wrap: break-word;'>请求/响应</td><td style='text-align: center; word-wrap: break-word;'>启动站请求从动站的响应，从动站做确认、否认或数据响应。</td></tr></table>

#### 5.4.2 平衡传输过程

### 适用信道

全双工接口可采用平衡传输规则。

### 发送 / 无回答

启动站允许建立一个通信服务，由启动站进行数据流控制。

#### 发送 / 确认

启动站允许建立一个通信服务，由启动站进行数据流控制。当从动站正确收到启动站报文时，并能执行启动站报文的命令，则发送确认帧；否则发送否认帧。

##### 请求 / 响应

启动站允许建立一个通信服务，由启动站进行数据流控制。从动站响应新的请求服务之前，必须完成前一个请求服务的响应。

对于需要应答的报文，若启动站在10秒内未收到从动站的应答报文，则重发原报义。里反次数个少于2次。

### 5.5 物理接口

串行通信传输接口

TTL 电平异步通信串行口。

## 6 用户数据结构

### 6.1 用户数据区格式

用户数据区的帧格式定义见下图。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>地址域 A</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>应用功能码 AFN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>帧序列域 SEQ</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>应用数据</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">图 4 用户数据区帧格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>说明：用户数据区中所有预留部分均用0填充。</td><td style='text-align: center; word-wrap: break-word;'>删除[狼 3]:</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>删除[狼 3]:</td></tr></table>

### 6.2 地址域 A

#### 6.2.1 地址域格式

地址域格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 3 地址域格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>地址域</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>源地址 ASRC</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>目的地址 ADST</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

a) 当控制域的“地址域标识”为0时，无地址域A；

b) 当控制域的“地址域标识”为1时，对于集中器本地接口，下行时，源地址是指集中器MAC地址；目的地址是目标电能表的MAC地址。上行时，目的地址是指集中器的MAC地址。

删除[狼3]:

源地址是指电能表的MAC地址。

删除[狼3]:

c）当为广播命令时，目的地址为广播地址 99 99 99 99 99 99 99 99。

### 6.3 应用数据域格式

应用数据域格式定义见下图。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//a4d92c9d-a2ea-40b6-a21b-dcbab2107676/markdown_3/imgs/img_in_image_box_467_895_774_1035.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A35Z%2F-1%2F%2Fdc3807948ede0bccc95c42ae3da210d4dc0787bf83508f811b8e9e4c5398ddc7" alt="Image" width="19%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 5 应用数据域格式</div> </div>


### 6.4 应用层功能码 AFN

#### 6.4.1 集中器应用功能码

集中器本地通信接口应用功能码 AFN由一字节组成，采用二进制编码表示，具体定义见下表。删除[狼 3]:

<div style="text-align: center;"><div style="text-align: center;">表 4 集中器本地通信模块接口应用功能码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>应用功能码AFN</td><td style='text-align: center; word-wrap: break-word;'>应用功能定义</td><td style='text-align: center; word-wrap: break-word;'>数据标识编码DI</td><td style='text-align: center; word-wrap: break-word;'>具体项目</td><td style='text-align: center; word-wrap: break-word;'>地址域标识（0 为不带地址域）</td></tr><tr><td rowspan="2">00H</td><td rowspan="2">确认/否认</td><td style='text-align: center; word-wrap: break-word;'>E8 01 00 01</td><td style='text-align: center; word-wrap: break-word;'>确认</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 01 00 02</td><td style='text-align: center; word-wrap: break-word;'>否认</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="3">01H</td><td rowspan="3">初始化模块</td><td style='text-align: center; word-wrap: break-word;'>E8 02 01 01</td><td style='text-align: center; word-wrap: break-word;'>复位硬件</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 01 02</td><td style='text-align: center; word-wrap: break-word;'>初始化档案</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 01 03</td><td style='text-align: center; word-wrap: break-word;'>初始化任务</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="2"></td><td rowspan="2"></td><td style='text-align: center; word-wrap: break-word;'>E8 02 02 01</td><td style='text-align: center; word-wrap: break-word;'>添加任务</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 02 02</td><td style='text-align: center; word-wrap: break-word;'>删除任务</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="25">02H</td><td rowspan="25">管理任务</td><td style='text-align: center; word-wrap: break-word;'>E8 00 02 03</td><td style='text-align: center; word-wrap: break-word;'>查询未完成任务数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 02 04</td><td style='text-align: center; word-wrap: break-word;'>查询未完成任务列表</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 02 04</td><td style='text-align: center; word-wrap: break-word;'>返回查询未完成任务列表</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 02 05</td><td style='text-align: center; word-wrap: break-word;'>查询未完成任务详细信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 02 05</td><td style='text-align: center; word-wrap: break-word;'>返回查询未完成任务详细信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 02 06</td><td style='text-align: center; word-wrap: break-word;'>查询剩余可分配任务数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 02 07</td><td style='text-align: center; word-wrap: break-word;'>添加多播任务（选配）</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 02 08</td><td style='text-align: center; word-wrap: break-word;'>启动任务</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 02 09</td><td style='text-align: center; word-wrap: break-word;'>暂停任务</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 01</td><td style='text-align: center; word-wrap: break-word;'>查询厂商代码和版本信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 02</td><td style='text-align: center; word-wrap: break-word;'>查询本地通信模块运行模式信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 03</td><td style='text-align: center; word-wrap: break-word;'>查询主节点地址</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 04</td><td style='text-align: center; word-wrap: break-word;'>查询通信延时时长</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 04</td><td style='text-align: center; word-wrap: break-word;'>返回查询通信延时时长</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 05</td><td style='text-align: center; word-wrap: break-word;'>查询从节点数量</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 06</td><td style='text-align: center; word-wrap: break-word;'>查询从节点信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 06</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 07</td><td style='text-align: center; word-wrap: break-word;'>查询从节点主动注册进度</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 08</td><td style='text-align: center; word-wrap: break-word;'>查询从节点的父节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 08</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点的父节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 09</td><td style='text-align: center; word-wrap: break-word;'>查询映射表从节点数量</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 0A</td><td style='text-align: center; word-wrap: break-word;'>查询从节点通信地址映射表</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 0A</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点通信地址映射表</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 03 0B</td><td style='text-align: center; word-wrap: break-word;'>查询任务建议超时时间</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 0C</td><td style='text-align: center; word-wrap: break-word;'>查询从节点相位信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="14">03H</td><td rowspan="14">读参数</td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 0C</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点相位信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 0D</td><td style='text-align: center; word-wrap: break-word;'>批量查询从节点相位信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 0D</td><td style='text-align: center; word-wrap: break-word;'>返回批量查询从节点相位信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 0E</td><td style='text-align: center; word-wrap: break-word;'>查询表档案的台区识别结果</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 0E</td><td style='text-align: center; word-wrap: break-word;'>返回查询表档案的台区识别结果</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 0F</td><td style='text-align: center; word-wrap: break-word;'>查询多余节点的台区识别结果</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 0F</td><td style='text-align: center; word-wrap: break-word;'>返回查询多余节点的台区识别结果</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 10</td><td style='text-align: center; word-wrap: break-word;'>查询台区识别状态</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 10</td><td style='text-align: center; word-wrap: break-word;'>返回查询台区识别状态</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 12</td><td style='text-align: center; word-wrap: break-word;'>批量查询厂商代码和版本信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 12</td><td style='text-align: center; word-wrap: break-word;'>批量返回查询厂商代码和版本信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 13</td><td style='text-align: center; word-wrap: break-word;'>查询模块资产信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 03 13</td><td style='text-align: center; word-wrap: break-word;'>返回查询模块资产信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 03 14</td><td style='text-align: center; word-wrap: break-word;'>批量查询模块资产信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr></table>







<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>应用功能码
AFN</td><td style='text-align: center; word-wrap: break-word;'>应用功能定义</td><td style='text-align: center; word-wrap: break-word;'>数据标识编码
DI</td><td style='text-align: center; word-wrap: break-word;'>具体项目</td><td style='text-align: center; word-wrap: break-word;'>地址域标识
(0为不带地址域)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 14</td><td style='text-align: center; word-wrap: break-word;'>批量返回查询模块资产信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 61</td><td style='text-align: center; word-wrap: break-word;'>查询从节点实时信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 61</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点实时信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 64</td><td style='text-align: center; word-wrap: break-word;'>查询设备在线状态</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 64</td><td style='text-align: center; word-wrap: break-word;'>返回设备在线状态</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 65</td><td style='text-align: center; word-wrap: break-word;'>查询网络拓扑信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 65</td><td style='text-align: center; word-wrap: break-word;'>返回网络拓扑信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 66</td><td style='text-align: center; word-wrap: break-word;'>查询节点运行时长</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 66</td><td style='text-align: center; word-wrap: break-word;'>返回节点运行时长</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 6A</td><td style='text-align: center; word-wrap: break-word;'>查询最大网络规模</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 6B</td><td style='text-align: center; word-wrap: break-word;'>查询最大网络允许级数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 6C</td><td style='text-align: center; word-wrap: break-word;'>查询允许/禁止拒绝从节点信息上报
开关</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 6D</td><td style='text-align: center; word-wrap: break-word;'>查询无线参数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 6E</td><td style='text-align: center; word-wrap: break-word;'>查询指定从节点信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 6E</td><td style='text-align: center; word-wrap: break-word;'>返回查询指定从节点信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 6F</td><td style='text-align: center; word-wrap: break-word;'>查询主节点运行信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 70</td><td style='text-align: center; word-wrap: break-word;'>查询节点自检结果</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 70</td><td style='text-align: center; word-wrap: break-word;'>返回查询节点自检结果</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 72</td><td style='text-align: center; word-wrap: break-word;'>查询踢出后不允许入网时间</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 74</td><td style='text-align: center; word-wrap: break-word;'>查询运行参数信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 74</td><td style='text-align: center; word-wrap: break-word;'>返回查询运行参数信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 90</td><td style='text-align: center; word-wrap: break-word;'>查询宽带载波频段</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 91</td><td style='text-align: center; word-wrap: break-word;'>查询多网络信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 93</td><td style='text-align: center; word-wrap: break-word;'>查询白名单生效信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 95</td><td style='text-align: center; word-wrap: break-word;'>查询并发数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 96</td><td style='text-align: center; word-wrap: break-word;'>查询设备类型</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 96</td><td style='text-align: center; word-wrap: break-word;'>返回查询设备类型</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 00 03 97</td><td style='text-align: center; word-wrap: break-word;'>查询台区组网成功率</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 03 03 98</td><td style='text-align: center; word-wrap: break-word;'>查询节点信道信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 04 03 98</td><td style='text-align: center; word-wrap: break-word;'>返回节点信道信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 01</td><td style='text-align: center; word-wrap: break-word;'>设置主节点地址</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 02</td><td style='text-align: center; word-wrap: break-word;'>添加从节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 03</td><td style='text-align: center; word-wrap: break-word;'>删除从节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 04</td><td style='text-align: center; word-wrap: break-word;'>允许/禁止上报从节点事件</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>写参数</td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 05</td><td style='text-align: center; word-wrap: break-word;'>激活从节点主动注册</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>04H</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 06</td><td style='text-align: center; word-wrap: break-word;'>终止从节点主动注册</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 07</td><td style='text-align: center; word-wrap: break-word;'>添加从节点通信地址映射表</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 6A</td><td style='text-align: center; word-wrap: break-word;'>设置最大网络规模</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="10"></td><td rowspan="10"></td><td style='text-align: center; word-wrap: break-word;'>E8 02 04 6B</td><td style='text-align: center; word-wrap: break-word;'>设置网络最大级数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 6C</td><td style='text-align: center; word-wrap: break-word;'>禁止/允许拒绝节点信息上报</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 6D</td><td style='text-align: center; word-wrap: break-word;'>设置无线参数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 72</td><td style='text-align: center; word-wrap: break-word;'>配置踢出后不允许入网时间</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 74</td><td style='text-align: center; word-wrap: break-word;'>设置从节点配置运行参数</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 80</td><td style='text-align: center; word-wrap: break-word;'>启动台区识别</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 81</td><td style='text-align: center; word-wrap: break-word;'>停止台区识别</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 90</td><td style='text-align: center; word-wrap: break-word;'>设置宽带载波频段</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 93</td><td style='text-align: center; word-wrap: break-word;'>禁止/允许白名单功能</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 04 F0</td><td style='text-align: center; word-wrap: break-word;'>重启节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="7">05H</td><td rowspan="7">上报信息</td><td style='text-align: center; word-wrap: break-word;'>E8 05 05 01</td><td style='text-align: center; word-wrap: break-word;'>上报任务数据</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 05 05 02</td><td style='text-align: center; word-wrap: break-word;'>上报从节点事件</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 05 05 03</td><td style='text-align: center; word-wrap: break-word;'>上报从节点信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 05 05 04</td><td style='text-align: center; word-wrap: break-word;'>上报从节点注册结束</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 05 05 05</td><td style='text-align: center; word-wrap: break-word;'>上报任务状态</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 05 05 06</td><td style='text-align: center; word-wrap: break-word;'>上报电能表数据</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 05 05 80</td><td style='text-align: center; word-wrap: break-word;'>上报非本台区从节点信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>06H</td><td style='text-align: center; word-wrap: break-word;'>请求信息</td><td style='text-align: center; word-wrap: break-word;'>E8 06 06 01</td><td style='text-align: center; word-wrap: break-word;'>请求集中器时间</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td rowspan="6">07H</td><td rowspan="6">传输文件</td><td style='text-align: center; word-wrap: break-word;'>E8 02 07 01</td><td style='text-align: center; word-wrap: break-word;'>启动文件传输</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 02 07 02</td><td style='text-align: center; word-wrap: break-word;'>传输文件内容</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 07 03</td><td style='text-align: center; word-wrap: break-word;'>查询文件信息</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 00 07 04</td><td style='text-align: center; word-wrap: break-word;'>查询文件处理进度</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 03 07 04</td><td style='text-align: center; word-wrap: break-word;'>查询文件传输失败节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8 04 07 04</td><td style='text-align: center; word-wrap: break-word;'>返回查询文件传输失败节点</td><td style='text-align: center; word-wrap: break-word;'>0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>F0H</td><td style='text-align: center; word-wrap: break-word;'>维护模块</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>厂家自定义</td><td style='text-align: center; word-wrap: break-word;'>......</td></tr></table>





### 6.5 帧序列域 SEQ

#### 6.5.1 帧序列域格式

帧序列域格式定义如下表。

<div style="text-align: center;"><div style="text-align: center;">表 5 帧序列域下行报文格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>帧序列号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 帧序列号：用以匹配上、下行报文的请求应答对应关系，值从0～255，循环使用。

删除[狼 3]:

### 6.6 数据标识编码 DI

#### 6.6.1 数据标识编码定义

数据标识编码 DI由四个字节构成，用来区分不同的数据标识，四个字节分别用 DI3，DI2，DI1和DI0代表，每字节采用十六进制编码。

#### 6.6.2 数据标识编码格式

数据标识编码格式定义见下图。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">图 6 数据格式编码方式</div> </div>


a) DI3: 通信双方类型标识, E8 表示集中器与本地模块通信。

b) DI2: 报文上下行类型及内容相关标识，

1）00 表示上下行均用，但下行无数据内容；

2）01 表示上下行均用，数据内容格式一致；

3）02 表示仅下行用，上行为确认/否认报文；

4）03 表示仅下行用，带数据内容。对应上行报文为 04；

5）04 表示仅上行用，带数据内容。对应下行报文为 03；

6）05 表示仅上行用，下行为确认/否认报文；

7）06 表示上下行均用，但上行无数据内容；

c） 集中器发送给本地模块的报文为下行报文；本地模块发送给集中器的报文为上行报文。

d) DI1: 功能码类型定义：与 AFN 值保持一致。

e) DIO: 功能码子类型。

#### 6.6.3 数据标识内容

数据标识内容为按数据标识所组织的数据，包括参数、命令等。简称为数据内容。

### 6.7 报文格式

集中器与本地模块交互的报文格式见下图。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>68H</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>L</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>C</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>A</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>AFN</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>SEQ</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>数据标识编码</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CS</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>16H</td></tr></table>

### 6.8 集中器应用数据报文结构

应用数据报文结构是对应用功能码及其对应的数据标识编码、数据标识内容进行详细的定义和说明。

#### 6.8.1 确认 / 否认（AFN=00H）

### 数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 6 确认/否认数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>确认</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>否认</td></tr></table>

数据标识内容定义

#### E8 01 00 01: 确认

数据标识内容格式见下表。

等待时间：该确认帧对应的命令的执行时间，单位为秒。

<div style="text-align: center;"><div style="text-align: center;">表 7 确认数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>等待时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

##### E8 01 00 02: 否认

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 8 否认数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>错误状态字</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

错误状态字：0 为通信超时，1 为无效数据标识内容，2 为长度错误，3 为校验错误，4 为数据标识编码不存在，5 为格式错误，6 为表号重复，7 为表号不存在，8 为电表应用层无应答，9 为主节点忙，10 主节点不支持此命令，11 为从节点不应答，12 为从节点不在网内，13 为添加任务时剩余可分配任务数不足，14 为上报任务数据时任务不存在，15 为任务 ID 重复，16 为查询任务时模块没有此任务，17 为任务 ID 不存在，FFH 其他。

#### 6.8.2 初始化模块（AFN=01H）

### 数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 9 初始化模块数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>复位硬件</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>初始化档案</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>初始化任务</td></tr></table>

下行报文

数据标识内容定义

E8 02 01 01：复位硬件

无数据标识内容。

E8 02 01 02: 初始化档案

无数据标识内容。

清除模块保存的档案信息。

清除模块保存的从节点通信地址映射表。

##### E8 02 01 03: 初始化任务

无数据标识内容。

清除模块保存的任务信息。

#### 上行报文

初始化模块的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。模块正确接收到初始化模块报文后立即回复确认帧，确认帧中的等待时间为模块完成初始化所需时间。

模块执行完初始化模块命令后，处于暂停任务状态。

#### 6.8.3 管理任务（AFN=02H）

##### 数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 10 管理任务数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>添加任务</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>删除任务</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>查询未完成任务数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>查询未完成任务列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>返回查询未完成任务列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>查询未完成任务详细信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>返回查询未完成任务详细信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>查询剩余可分配任务数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>添加多播任务</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>08</td><td style='text-align: center; word-wrap: break-word;'>启动任务</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>09</td><td style='text-align: center; word-wrap: break-word;'>暂停任务</td></tr></table>

下行报文

数据标识内容定义

#### E8 02 02 01：添加任务

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 11 添加任务数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="8">数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td colspan="8">任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">任务模式字</td><td rowspan="2"></td><td rowspan="2"></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>D0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务响应标识</td><td style='text-align: center; word-wrap: break-word;'>转发标识</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td colspan="4">任务优先级</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td colspan="8">超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">报文长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">报文内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>

a）任务 ID：区分不同任务的任务标识。本标准的任务 ID 取值范围为 0x0000-0xEFFF，其他取值保留。任务 ID 号必须在取值范围内循环使用，同一个任务 ID 号不能连续用在不同的任务中。

b) 任务优先级：0~3，0 表示最高优先级，3 表示最低优先级。由集中器指定任务的优先级，模块保证高优先级的任务得到优先执行。

c) 任务响应标识：该任务是否需要返回数据，0－不需要数据返回，1－需要数据返回。由集中器指定，广播校时等任务为 0，抄表任务为 1。若任务响应标识为 0，则模块只向集中器上报任务状态，不上报任务数据。

d) 转发标识：默认为 0，若该任务需要下达给通信模块，将该位置为 1。

e）超时时间：集中器指定任务执行的超时时间，单位为秒。超时时间从模块正确接收完集中器下发任务时开始计时，超时时间结束，集中器删除自己保存的任务，再按需决定是否重新下发；模块在超时时间结束时，若未完成任务，应上报任务状态不成功。

f) 报文长度：原始报文数据总长度。

g）报文内容：当转发标识为1时，报文第一位为“业务代码”，如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 12 报文内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="2">数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td rowspan="2">报文内容</td><td style='text-align: center; word-wrap: break-word;'>业务代码</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文有效内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>L-1</td></tr></table>

h）业务代码：00H-透传报文；01H-精准对时；02-DLMS报文；其他一保留。

当业务代码为01H时，报文内容为校时报文，具体格式见A.7；

#### E8 02 02 02: 删除任务

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 13 删除任务数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

任务 ID：区分不同任务的任务标识。本标准的任务 ID 取值范围为 0x0000-0xEFFF，其他取值保留。

#### E8 00 02 03: 查询未完成任务数

无数据标识内容。用于查询模块中尚未执行完毕的任务数。

#### E8 03 02 04: 查询未完成任务列表

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 14 查询未完成任务列表数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>起始任务序号 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次查询的任务数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）起始任务序号 m：任务的起始序号，表示在任务列表中的第 m 个任务，序号从 0 开始。

b) 本次查询的任务数量 n：本次查询的任务个数，起始序号为 m，任务数量为 n，表示查询任务列表中的第 m, m+1，……，m+n-1 个任务，n≥1。

### E8 03 02 05: 查询未完成任务详细信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 15 查询未完成任务详细信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>





任务 ID: 区分不同任务的任务标识。

#### E8 00 02 06: 查询剩余可分配任务数

无数据标识内容。

#### E8 02 02 07: 添加多播任务（选配）

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 16 添加多播任务数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="8">数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td colspan="8">任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">任务模式字</td><td rowspan="2">BS</td><td rowspan="2">1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>DO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务响应标识</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td colspan="4">任务优先级</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td colspan="8">从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">从节点地址 1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td colspan="8">……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td colspan="8">从节点地址 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td colspan="8">超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">报文长度 L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">报文内容</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>

a）任务ID：区分不同任务的任务标识。

b) 任务优先级：0~3,0 表示最高优先级，3 表示最低优先级。由集中器来指定任务的优先级，模块保证高优先级的任务得到优先执行。

c）任务响应标识：该任务是否需要返回数据，0－不需要数据返回，1－数据返回。由集中器指定，广播校时等任务为0，抄表任务为1。若任务响应标识为0，则模块只向集中器上报任务状态，不上报任务数据。

d) 超时时间：集中器指定任务执行的超时时间，单位为秒。超时时间从模块正确接收完集中器下发任务时开始计时，超时时间结束，集中器删除自己保存的任务，再按需决定是否重新下发；模块在超时时间结束时，若未完成任务，应上报任务状态不成功。

e) 从节点数量：多播抄表的数量。数量 0xFFFF 表示向所有从模块传输任务报文。

f) 从节点地址：多播抄表的地址。从节点数量为 n 时，表示多播同时抄读 n 个地址的某个数据项。若节点数量为 0xFFFF，则无从节点地址域。

g）报文长度：原始报文数据总长度。

h）报文内容：原始报文数据。

i）多播任务需要数据返回，则按照单播任务上报任务数据的格式上报集中器。

##### E8 02 02 08: 启动任务

无数据标识内容。

模块上电后，默认处于任务暂停状态，需要集中器下发启动任务。

#### E8 02 02 09: 暂停任务

无数据标识内容。

需要插入立即执行的任务时，可以先 “暂停任务”，然后通过 “添加任务” 增加高优先级的任务，再 “启动任务”。

### 上行报文

### 数据标识内容定义

E8 02 02 01：添加任务

添加任务的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

#### E8 02 02 02: 删除任务

删除任务的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

E8 00 01 03：查询未完成任务数

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 17 查询未完成任务数数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>未完成任务数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a）未完成任务数：表示已经下发到模块，模块已缓存但尚未执行或正在执行的任务。模块上报任务结果后，集中器回确认帧，模块可将已完成任务删除。

#### E8 04 02 04: 返回查询未完成任务列表

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 18 返回查询未完成任务列表数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次上报的任务数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 1 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 2 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 n ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

由于任务执行状态可能产生变化，模块上报的任务数量必须小于或等于集中器查询的任务数量。上报的任务数量  $ n \geqslant 0 $。

#### E8 04 02 05：返回查询未完成任务详细信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 19 查询未完成任务详细信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="8">数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td colspan="8">任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">任务模式字</td><td rowspan="3">BS</td><td rowspan="3">1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>D0</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务响应标识</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>保留</td><td colspan="4">任务优先级</td></tr><tr><td colspan="8">任务目的地址个数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td colspan="8">任务目的地址 1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td colspan="8">……</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td colspan="8">任务目的地址 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>





a）任务ID：区分不同任务的任务标识。

b) 任务优先级：0~3,0 表示最高优先级，3 表示最低优先级。由集中器来指定任务的优先级，模块保证高优先级的任务得到优先执行。

c）任务响应标识：该任务是否需要返回数据，0－不需要数据返回，1－需要数据返回。由集中器指定，广播校时等任务为0，抄表任务为1。

d）任务目的地址个数：任务下发的目的地址个数。普通任务时 n=1，多播任务 n>1。

e) 任务目的地址：任务下发的从节点地址。

f）报文长度：原始任务报文数据总长度。

g）报文内容：原始任务报文数据。

h）若任务已执行完毕或者任务ID不存在，则回复否认（任务ID不存在）。

#### E8 00 02 06: 查询剩余可分配任务数

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 20 查询剩余可分配任务数数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>剩余可分配任务数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

模块上电进行模块识别时，集中器可读取模块剩余可分配任务数作为参考，进行任务管理初始化，在分配任务时也可作为参考。

一个典型任务的大小为 24 字节，模块结合自身可用存储空间的大小，计算剩余可分配的任务数。模块至少能缓存 100 个典型任务。

剩余可分配任务数仅为集中器管理任务提供参考，当集中器添加任务的长度超过模块剩余存储空间时，模块回复否认。

##### E8 02 02 07：添加多播任务（选配）

添加任务的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

E8 02 02 08: 启动任务

启动任务的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

E8 02 02 09：暂停任务

暂停任务的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

#### 6.8.4 读参数（AFN=03H）

#### 数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 21 读参数数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>查询厂商代码和版本信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>查询本地通信模块运行模式信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>查询主节点地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>查询通信延时时长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>返回查询通信延时时长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>查询从节点数量</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>查询从节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>查询从节点主动注册进度</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>08</td><td style='text-align: center; word-wrap: break-word;'>查询从节点的父节点</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>08</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点的父节点</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0A</td><td style='text-align: center; word-wrap: break-word;'>查询从节点通信地址映射表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0A</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点通信地址映射表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0B</td><td style='text-align: center; word-wrap: break-word;'>查询任务建议超时时间</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0C</td><td style='text-align: center; word-wrap: break-word;'>查询从节点相位信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0C</td><td style='text-align: center; word-wrap: break-word;'>返回查询从节点相位信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0D</td><td style='text-align: center; word-wrap: break-word;'>批量查询从节点相位信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0D</td><td style='text-align: center; word-wrap: break-word;'>返回批量查询从节点相位信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0E</td><td style='text-align: center; word-wrap: break-word;'>查询本台区多余节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0E</td><td style='text-align: center; word-wrap: break-word;'>返回查询本台区多余节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0F</td><td style='text-align: center; word-wrap: break-word;'>查询台区识别状态</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>0F</td><td style='text-align: center; word-wrap: break-word;'>返回查询台区识别状态</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>10</td><td style='text-align: center; word-wrap: break-word;'>批量查询厂商代码和版本信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>10</td><td style='text-align: center; word-wrap: break-word;'>批量返回查询厂商代码和版本信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>查询模块资产信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>12</td><td style='text-align: center; word-wrap: break-word;'>返回查询模块资产信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>13</td><td style='text-align: center; word-wrap: break-word;'>批量查询模块资产信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>13</td><td style='text-align: center; word-wrap: break-word;'>批量返回查询模块资产信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>61</td><td style='text-align: center; word-wrap: break-word;'>查询从节点实时信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>61</td><td style='text-align: center; word-wrap: break-word;'>批量查询从节点实时信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>查询设备在线状态</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>64</td><td style='text-align: center; word-wrap: break-word;'>返回设备在线状态</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>65</td><td style='text-align: center; word-wrap: break-word;'>查询网络拓扑信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>65</td><td style='text-align: center; word-wrap: break-word;'>返回网络拓扑信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>66</td><td style='text-align: center; word-wrap: break-word;'>查询节点运行时长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>66</td><td style='text-align: center; word-wrap: break-word;'>返回节点运行时长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6A</td><td style='text-align: center; word-wrap: break-word;'>查询最大网络规模</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6B</td><td style='text-align: center; word-wrap: break-word;'>查询最大网络允许级数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6C</td><td style='text-align: center; word-wrap: break-word;'>查询允许/禁止拒绝从节点信息上报</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6D</td><td style='text-align: center; word-wrap: break-word;'>查询无线参数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6E</td><td style='text-align: center; word-wrap: break-word;'>查询指定从节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6E</td><td style='text-align: center; word-wrap: break-word;'>返回查询指定从节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>6F</td><td style='text-align: center; word-wrap: break-word;'>查询主节点运行信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>70</td><td style='text-align: center; word-wrap: break-word;'>查询节点自检结果</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>70</td><td style='text-align: center; word-wrap: break-word;'>返回节点自检信息</td></tr></table>







<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>72</td><td style='text-align: center; word-wrap: break-word;'>查询踢出后不允许入网时间</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>74</td><td style='text-align: center; word-wrap: break-word;'>查询查询运行参数信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>74</td><td style='text-align: center; word-wrap: break-word;'>返回查询运行参数信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>90</td><td style='text-align: center; word-wrap: break-word;'>查询宽带载波频段</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>91</td><td style='text-align: center; word-wrap: break-word;'>查询多网络信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>93</td><td style='text-align: center; word-wrap: break-word;'>查询白名单生效信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>95</td><td style='text-align: center; word-wrap: break-word;'>查询并发数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>96</td><td style='text-align: center; word-wrap: break-word;'>查询设备类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>96</td><td style='text-align: center; word-wrap: break-word;'>返回查询设备类型</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>97</td><td style='text-align: center; word-wrap: break-word;'>查询台区组网成功率</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>98</td><td style='text-align: center; word-wrap: break-word;'>查询节点信道信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>98</td><td style='text-align: center; word-wrap: break-word;'>返回节点信道信息</td></tr></table>

### 下行报文

### 数据标识内容定义

E8 00 03 01：查询厂商代码和版本信息

无数据标识内容。

E8 00 03 02：查询本地通信模块运行模式信息

无数据标识内容。

#### E8 00 03 03: 查询主节点地址

无数据标识内容。

#### E8 03 03 04: 查询通信延时时长

数据标识内容格式见下表。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信目的地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度 L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">表 22 查询通信延时时长数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信目的地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度 L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a）通信目的地址，其中，99 99 99 99 99 99 表示广播地址。

b) 报文长度 L：需要计算通信下行延时的报文长度。

#### E8 00 03 05: 查询从节点数量

无数据标识内容。查询主模块记录的从节点数量。仅限于查询通过“添加从节点”命令下发的从节点数量。

#### E8 03 03 06: 查询从节点信息

数据标识内容格式见下表。

### 表 23 查询从节点信息数据标识内容格式



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。

b) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1, ..., m+n-1 个从节点，n≥1。

#### E8 00 03 07: 查询从节点主动注册进度

无数据标识内容。

#### E8 03 03 08：查询从节点的父节点

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 24 查询从节点的父节点数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

E8 00 03 09: 查询映射表从节点数量

无数据标识内容。查询主模块记录的从节点数量。仅限于查询通过“添加从节点通信地址映射表”命令下发的从节点数量。

##### E8 03 03 OA：查询从节点通信地址映射表

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 25 查询从节点通信地址映射表数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>映射表记录起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>查询的映射表数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 映射表记录起始序号 m：表示在从节点通信地址映射记录在列表中的第 m 个从节点，序号从 0 开始。

#### E8 00 03 OB: 查询任务建议超时时间

无数据标识内容。

#### E8 03 03 0C: 查询从节点相位信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 26 查询从节点相位信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次查询从节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

a) 从节点数量 n 需满足： $ 0 < n \leq 16 $。

#### E8 03 03 OD：批量查询从节点相位信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 27 批量查询从节点相位信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。

b) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第  $ m, m+1, \ldots, m+n-1 $ 个从节点， $ n \geqslant 1 $。

#### E8 03 03 0E：查询表档案的台区识别结果

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 28 查询表档案的台区识别结果数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。

b) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第  $ m, m+1, \ldots, m+n-1 $ 个从节点， $ n \geq 1 $。

#### E8 03 03 0F：查询多余节点的台区识别结果

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 29 查询多余节点的台区识别结果数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。

b) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1, ..., m+n-1 个从节点，n≥1。

##### E8 03 03 10: 查询台区识别状态

无数据标识内容。

#### E8 03 03 12 批量查询厂商代码和版本信息

数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 30 批量查询厂商代码和版本信息</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点数量n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始，0 表示 CCO，1 表示第 1 个从节点，2 表示第 2 个从节点，以此类推。每次查询的节点数量建议不超过 15 个。

从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1，……，m+n-1 个从节点，n≥1。

#### E8 03 03 13: 查询模块资产信息

数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 31 查询模块资产信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息列表元素数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 ID1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 IDn</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）节点地址：填写主节点地址时表示查询 CCO 的资产信息；填写节点入网地址时表示查询相应 STA 的资产信息；

b) 信息列表元素数量 n：本次查询信息元素总数量；

c) 信息元素 ID：信息元素 ID 如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 32 信息元素 ID</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 ID 取值</td><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>字母或数字</td><td style='text-align: center; word-wrap: break-word;'>示例</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x00</td><td style='text-align: center; word-wrap: break-word;'>厂商代码</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XX(ASCII)</td><td style='text-align: center; word-wrap: break-word;'>如“南方电网”代号可为“NW”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x01</td><td style='text-align: center; word-wrap: break-word;'>软件版本号（模块）</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XXXX(BCD)</td><td style='text-align: center; word-wrap: break-word;'>如“0001”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x02</td><td style='text-align: center; word-wrap: break-word;'>Bootloader 版本号</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>XX(BIN)</td><td style='text-align: center; word-wrap: break-word;'>如“01”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x05</td><td style='text-align: center; word-wrap: break-word;'>芯片厂商代码</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XX(ASCII)</td><td style='text-align: center; word-wrap: break-word;'>如“南方电网”代号可为“NW”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x06</td><td style='text-align: center; word-wrap: break-word;'>软件发布日期（模块）</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD(BIN)</td><td style='text-align: center; word-wrap: break-word;'>如“210425”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x08</td><td style='text-align: center; word-wrap: break-word;'>模块出厂通信地址</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>XXXXXX(BIN)</td><td style='text-align: center; word-wrap: break-word;'>当通信模块不支持模块出厂通信地址或者读取错误时，填写全FF。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x09</td><td style='text-align: center; word-wrap: break-word;'>硬件版本号（模块）</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XXXX(BCD)</td><td style='text-align: center; word-wrap: break-word;'>如“0001”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0A</td><td style='text-align: center; word-wrap: break-word;'>硬件发布日期（模块）</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD(BIN)</td><td style='text-align: center; word-wrap: break-word;'>如“210425”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0B</td><td style='text-align: center; word-wrap: break-word;'>软件版本号（芯片）</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XXXX(BCD)</td><td style='text-align: center; word-wrap: break-word;'>如“0001”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0C</td><td style='text-align: center; word-wrap: break-word;'>软件发布日期（芯片）</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD(BIN)</td><td style='text-align: center; word-wrap: break-word;'>如“210425”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0D</td><td style='text-align: center; word-wrap: break-word;'>硬件版本号（芯片）</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XXXX(BCD)</td><td style='text-align: center; word-wrap: break-word;'>如“0001”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0E</td><td style='text-align: center; word-wrap: break-word;'>硬件发布日期（芯片）</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD(BIN)</td><td style='text-align: center; word-wrap: break-word;'>如“210425”</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x0F</td><td style='text-align: center; word-wrap: break-word;'>应用程序版本号</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>XXXX(BCD)</td><td style='text-align: center; word-wrap: break-word;'>填写“0001”</td></tr></table>

注：资产信息数据应符合低字节在前高字节在后的字节序（小端）。

#### E8 03 03 14: 批量查询模块资产信息

数据标识内容格式如表72所示。

<div style="text-align: center;"><div style="text-align: center;">表 33 查询模块资产信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>





a）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始，0 表示 CCO，1 表示第 1 个从节点，2 表示第 2 个从节点，以此类推。

b) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1，……，m+n-1 个从节点，n≥1。

c) 信息元素 ID：一次查询一个信息元素。

### E8 03 03 61：查询从节点实时信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 34 查询从节点实时信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

##### E8 03 03 64: 查询设备在线状态

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 35 查询设备在线状态数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

#### E8 03 03 65: 查询网络拓扑信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 36 查询网络拓扑信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a） 节点序号从 0 开始，数量 n 取值少于支持单次读写从节点信息的最大数量。

### E8 03 03 66: 查询节点运行时长

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 37 查询节点运行时长数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

E8 00 03 6A：查询最大网络规模

无数据标识内容。

E8 00 03 6B：查询最大网络级数

无数据标识内容。

E8 00 03 6C：查询允许/禁止拒绝从节点信息上报

无数据标识内容。

##### E8 00 03 6D: 查询无线参数

无数据标识内容。

#### E8 03 03 6E：查询指定从节点信息

数据标识内容格式见下表。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

##### E8 00 03 6F：查询主节点运行信息

无数据标识内容。

##### E8 03 03 70: 查询节点自检结果

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 38 查询节点自检结果数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

节点地址：节点的MAC地址

#### E8 00 03 72: 查询踢出后不允许入网时间

无数据标识内容。

##### E8 03 03 74：查询运行参数信息

<div style="text-align: center;"><div style="text-align: center;">表 39 查询运行参数信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行参数总数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行参数ID1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行参数ID2</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...。</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

运行参数ID取值如下：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>运行参数ID</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x01</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>从节点RF发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x02</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>从节点PLC发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x03</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>异常离网锁定时间，单位：分钟，默认30分钟</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x04</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>RF通道控制开关：0：关闭；1：开启；默认开启</td></tr></table>

##### E8 00 03 90: 查询宽带载波频段

无数据标识内容。

E8 00 03 91：查询多网络信息

无数据标识内容。

E8 00 03 93: 查询白名单生效信息

下行无数据体内容

##### E8 00 03 95: 查询宽带载波频段

无数据标识内容。

#### E8 03 03 96: 查询设备类型



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点数量n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

##### E8 00 03 97: 查询台区组网成功率

无数据标识内容。

E8 03 03 98: 查询节点信道信息



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）节点地址：表地址。STA 是入网 MAC 地址

b) 周边节点起始序号 m：表示在周边节点列表中的第 m 个从节点，序号从 0 开始。

c) 周边节点数量 n ： 周边节点起始序号为 m ， 节点数量为 n ， 表示查询周边节点列表中的第 m, m+1 ， 。 。 ， m+n-1 个从节点， 每一次查询 6 个（6≥n≥1）。

上行报文

#### 数据标识内容定义

#### E8 00 03 01：查询厂商代码和版本信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 40 厂商代码和版本信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>厂商代码</td><td style='text-align: center; word-wrap: break-word;'>ASCII</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>芯片代码</td><td style='text-align: center; word-wrap: break-word;'>ASCII</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本时间</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

#### E8 00 03 02: 查询本地通信模块运行模式信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 41 本地通信模块运行模式信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="7">数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td colspan="7">本地通信模式字</td><td style='text-align: center; word-wrap: break-word;'>BS</td><td rowspan="3">1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>D0</td></tr><tr><td colspan="4">保留</td><td colspan="4">通信方式</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>最大支持的协议报文长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件传输支持的最大单包长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>升级操作等待时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>支持的最大从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>支持单次读写从节点信息的最大数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信模块接口协议发布日期</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>厂商代码和版本信息</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>9</td></tr></table>

a）通信方式：1表示“窄带电力线载波通信”，2表示“宽带电力线载波通信”，3表示“微功率无线通信”，4表示“窄带+微功率无线”，5表示“宽带+微功率无线”，其他取值保留。

b) 最大支持的协议报文长度：可以正确接收的协议报文最大长度。

c）文件传输支持的最大单个数据包长度：在AFN07H“传输文件”中支持的最大“文件段长度”大小。最大长度的值应在64、128、256、512、1024中选择。

d) 升级操作等待时间：终端发送完最后一个升级数据包且文件已经生效之后，需要等待模块完成升级的时间长度。单位为分钟。

e) 主节点地址：本地通信模块的主节点地址。

f) 支持的最大从节点数量：主节点模块支持的最大从节点下装数量。

g) 当前从节点数量：主节点模块当前下装的从节点数量。

h) 单次读写从节点信息的最大数量：添加/删除/查询从节点等读写从节点信息时，一次支持最大的从节点数量。

i）通信模块接口协议发布日期：BCD编码，YYMMDD日期格式。本标准发布日期为XXXXXX（具体待定）。本次协议新增设备在线、网络拓扑、节点运行时长、从节点入网被拒信息、节点自检结果、应用层报文信息、宽带载波频段、多网络信息、并发数、台区组网成功率、节点信道信息别等内容。

j）通信模块厂商代码及版本信息：与 AFN=03H-DI=E8 00 03 01 查询“厂商代码及版本信息”返回内容相同。

#### E8 00 03 03：查询主节点地址

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 42 主节点地址数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

#### E8 04 03 04：返回查询通信延时时长

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 43 通信延时时长数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信目的地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>通信延时时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a）通信目的从节点地址，其中，99 99 99 99 99 99 表示广播地址。

b）通信延时时长：代表预计该长度报文在当前通信环境需要的具体通信延时，单位秒。

c) 报文长度 L：当前计算通信下行延时的报文长度。

#### E8 00 03 05: 查询从节点数量

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 44 查询从节点数量数据单元格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

#### E8 04 03 06: 返回查询从节点信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 45 返回查询从节点信息数据单元格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的从节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节地址 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

数据标识内容格式见下表。

### E8 00 03 07: 查询从节点主动注册进度

<div style="text-align: center;"><div style="text-align: center;">表 46 查询从节点主动注册数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点主动注册工作标识</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

从节点主动注册工作标示：0 为从节点停止主动注册，1 为从节点正在主动注册。

### E8 04 03 08: 返回查询从节点的父节点

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 47 查询从节点的父节点数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>父节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>链路质量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）链路质量：从节点与其父节点之间通信链路的链路质量。范围为0~31。31最佳，0最差。E8 00 03 09：查询映射表从节点数量

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 48 查询映射表从节点数量数据单元格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>映射表从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

##### E8 04 03 OA：返回查询从节点通信地址映射表

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 49 返回查询节点通信地址映射表数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>映射表记录节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的映射表记录数量n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点1通信地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点1表计地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点n通信地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点n表计地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>12</td></tr></table>

注 1：每个从节点通信映射地址（18 字节）组成：通信地址（6 字节）+表计地址（12 字节）。

##### E8 00 03 OB：查询任务建议超时时间

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 50 任务建议超时时间数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>优先级 0 的任务建议超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>优先级 1 的任务建议超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>优先级 2 的任务建议超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>优先级 3 的任务建议超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a） 超时时间：单位 s，最长为 65535s，约 18 小时。

b) 建议集中器每下发 20 个任务，至少查询一次模块的建议超时时间。两次查询之间的时间间隔不得超过 20 分钟。集中器根据模块的建议超时时间动态调整抄表策略，提高抄表效率。

c) 模块需根据当前通信网络状态、未执行任务数量等信息，向集中器提供后续任务的建议超时时间。由于集中器每下发 20 个任务均需查询一次建议超时时间，因此模块可在执行 20 个任务的假设下，计算建议超时时间。

##### E8 04 03 0C: 返回查询从节点相位信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 51 返回查询从节点相位信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的从节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 相位信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节地址 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 相位信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

#### E8 04 03 OD：返回批量查询从节点相位信息

数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 52 返回批量查询从节点相位信息数据标识内容格式</div> </div>




<table border="1" style="margin: auto; word-wrap: break-word;"><tr><td style="text-align: center; word-wrap: break-word;">数据内容</td><td style="text-align: center; word-wrap: break-word;">数据格式</td><td style="text-align: center; word-wrap: break-word;">字节数</td></tr><tr><td style="text-align: center; word-wrap: break-word;">从节点总数量</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr><tr><td style="text-align: center; word-wrap: break-word;">本次应答的从节点数量n</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">1</td></tr><tr><td style="text-align: center; word-wrap: break-word;">从节点1地址</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">6</td></tr><tr><td style="text-align: center; word-wrap: break-word;">从节点1相位信息</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr><tr><td style="text-align: center; word-wrap: break-word;">……</td><td style="text-align: center; word-wrap: break-word;">……</td><td style="text-align: center; word-wrap: break-word;">……</td></tr><tr><td style="text-align: center; word-wrap: break-word;">从节点n地址</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">6</td></tr><tr><td style="text-align: center; word-wrap: break-word;">从节点n相位信息</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr></table>




对 “从节点相位信息” 扩展如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 53 从节点相位信息数据标识内容</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="8">数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>D0</td><td rowspan="2">BS</td><td rowspan="2">1</td></tr><tr><td colspan="3">相序类型</td><td colspan="2">相线特征</td><td colspan="3">相线标识</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>D4</td><td style='text-align: center; word-wrap: break-word;'>D3</td><td style='text-align: center; word-wrap: break-word;'>D2</td><td style='text-align: center; word-wrap: break-word;'>D1</td><td style='text-align: center; word-wrap: break-word;'>D0</td><td rowspan="2">BS</td><td rowspan="2">1</td></tr><tr><td colspan="2">模块类型</td><td colspan="3">保留</td><td colspan="3">规约类型</td></tr></table>

a）相线标识：D0、D1、D2依次表示第1、2、3相，置“1”表示电表接入对应相位，置“0”表示未接入该相位或该相位断相。

b) 相线特

c) 相序类型：D7～D5 如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 54 相序类型数据格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>D7</td><td style='text-align: center; word-wrap: break-word;'>D6</td><td style='text-align: center; word-wrap: break-word;'>D5</td><td style='text-align: center; word-wrap: break-word;'>相序表示</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>三相表 ABC（正常相序）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>三相表 ACB（逆相序）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>三相表 BAC（逆相序）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>三相表 BCA（逆相序）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>三相表 CAB（逆相序）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>三相表 CBA（逆相序）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>三相表/单相表零火反接</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

当断相三相电表存在断相时，相序类型填写“保留”。

a） 单相表默认填写 “000”，零火反接时填写 “110”

b）规约类型：OH：未知规约；O4H：DLMS规约；其他值保留。

c）模块类型：01，单相电表模块；10，三相电表模块；其他值保留。

E8 04 03 0E：返回查询表档案的台区识别结果

<div style="text-align: center;"><div style="text-align: center;">表 55 返回查询表档案的台区识别结果数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>台区识别结果从节点总数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点总数量 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址 1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 1 台区识别结果</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 m 台区识别结果</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>





a) 返回结果中的从节点为通过“添加从节点”设置的从节点。

b) 台区识别结果：0 表示该节点属于本台区；1 表示该节点不属于本台区；2 表示该节点无法通信；3 表示未知；4 表示不支持台区识别功能，适用于微功率无线通信方案；其他值保留。

#### E8 04 03 OF：返回查询多余节点的台区识别结果

<div style="text-align: center;"><div style="text-align: center;">表 56 返回查询多余节点的台区识别结果数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>台区识别结果从节点总数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点总数量 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址 1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 1 属性（保留）</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 m 属性（保留）</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr></table>

a) 返回结果中的从节点指与主节点处于同一台区且能与主节点通信的从节点。

节点属性格式如下表

<div style="text-align: center;"><div style="text-align: center;">表 57 节点属性格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上一所属台区主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

E8 04 03 10: 返回查询台区识别状态

数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 58 返回查询台区识别状态数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>台区识别状态</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>剩余时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）台区识别状态：0，表示未识别或识别完成或识别停止；1，表示识别中；

b) 剩余时长格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 59 剩余时长内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>台区识别状态</td><td style='text-align: center; word-wrap: break-word;'>剩余时长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>0xFF</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>根据参数 E8 02 04 80 命令，计算的剩余时长（分钟）</td></tr></table>

剩余时间计算方式为：剩余时间=台区特征发送时长-已进行识别时长

### E8 04 03 12：批量返回查询厂商代码和版本信息

数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 60 批量返回查询厂商代码和版本信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点总数量 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的从节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点1 地址</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点1 信息</td><td style='text-align: center; word-wrap: break-word;'>BS</td><td style='text-align: center; word-wrap: break-word;'>9</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点n 地址</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点n 信息</td><td style='text-align: center; word-wrap: break-word;'>BS</td><td style='text-align: center; word-wrap: break-word;'>9</td></tr></table>

说明：

节点总数量 m 包括 CCO 和全部 STA 在内；

节点地址，指 MAC 地址；

节点信息如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 61 节点信息内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>厂商代码</td><td style='text-align: center; word-wrap: break-word;'>ASCII</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>芯片代码</td><td style='text-align: center; word-wrap: break-word;'>ASCII</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本时间</td><td style='text-align: center; word-wrap: break-word;'>YYMMDD</td><td style='text-align: center; word-wrap: break-word;'>3</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>版本号</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">E8 04 03 13: 返回查询模块资产信息</div> </div>


数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 62 返回查询模块资产信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 ID1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 1 长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 1 数据</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>变长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'>...</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 IDn</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 n 长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 n 数据</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>变长</td></tr></table>

#### E8 04 03 14: 批量返回查询模块资产信息

数据标识内容格式如表73所示。

<div style="text-align: center;"><div style="text-align: center;">表 63 返回查询模块资产信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的从节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信息元素 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 信息元素数据</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>变长</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 信息元素数据</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>变长</td></tr></table>

### E8 04 03 61：返回查询从节点实时信息

数据标识内容格式见下表所示。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点实时信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>-</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">从节点实时信息</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点运行时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>下行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点邻居网络总数 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1#邻居网络标识号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1#邻居网络 CCO 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1#邻居网络 HPLC 通道通信质量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...。</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

a） 节点运行时间：从节点从上电运行到现在的时间，单位：秒。

b）上行通信成功率：代理接收从节点的通信成功率。

c）下行通信成功率：从节点接收代理的通信成功率。

d) 从节点邻居网络总数：从节点设备监听到的邻居网络总数。

e) 网络标识号（SNID）： 是用于标识一个载波通信网络的唯一身份识别号。有效取值范围为 1~15。

f) 邻居网络 CCO 地址：从节点设备监听到的某个邻居网络 CCO 模块的地址，6 字节。

g) 邻居网络 HPLC 通道通信质量：从节点设备在 HPLC 通道监听某个邻居网络，如果入网此网络，与选择的代理之间的通信质量值，代表与此网络的通信效果；建议采用 RSSI 值，RSSI<-110 dBm 时，量化值=0，RSSI≥-110 dBm 时，量化值=RSSI+111。

#### E8 04 03 64: 返回查询设备在线状态

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 64 返回查询设备在线状态数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>入网节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 0 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 n-1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

a）节点序号从0开始，数量n取值少于支持单次读写从节点信息的最大数量；

### E8 04 03 65: 返回查询网络拓扑信息

数据标识内容格式见下表。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 0 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 0 网络拓扑信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>13</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 n-1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 n-1 网络拓扑信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>13</td></tr></table>

a）节点序号从 0 开始，其中 0 为主节点，后续为从节点；

b) 每次查询必须从序号 0 起始查询。

节点网络拓扑信息，见下表。

<div style="text-align: center;"><div style="text-align: center;">表 66 网络拓扑信息数据单元格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点标识</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理节点标识</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点加入网络时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理变更次数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>离线次数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）节点标识：D0-D11 本站点的节点标识（TEI），最大不超过 1024；

D12-D15: 模块类型, 0 为单载波模块、1 为双模模块、2 为无线模块;

b) 代理节点标识：本站点的代理站点节点标识（TEI）；

c） 节点加入网络时间：以主节点上电时为初始时间，从节点加入网络的时间，单位为秒；

d) 代理变更次数：节点代理变更次数；

e) 离线次数：节点离线次数；

f) 节点信息：D0～D3 位，节点层级，本站点的网络层级，0 级代表 0 层级，以此类推；D4～D6 位；节点角色，本站点的网络角色，0x0：无效，0x1：末梢节点（STA），0x2：代理节点（PCO），0x3：保留，0x4：主节点（CCO）；D7 位：节点和父节点的网络信道，0：载波，1：无线。

##### E8 04 03 66: 返回节点运行时长

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 67 返回节点运行时长数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

a）运行时长：当前节点从上电运行到现在的时间，如果主节点没有将从节点的运行时间查回来，默认为 0，单位为秒。

##### E8 00 03 6A：返回最大网络规模

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 68 返回最大网络规模数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大网络规模</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

#### E8 00 03 6B: 返回最大网络级数

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 69 返回最大网络级数数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大网络级数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

#### E8 00 03 6C：返回查询允许/禁止拒绝从节点信息使能

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>拒绝从节点信息上报使能</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a） 拒绝从节点信息上报使能：0：禁止；1：允许；

##### E8 00 03 6D: 返回无线参数

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 70 返回并发数数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>OPTION</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CHANNEL</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

E8 04 03 6E：返回查询指定从节点信息

数据标识内容格式如表所示。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>-</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">从节点信息</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>相位</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网络状态</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>载波通道接收质量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>无线通道接收质量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>系统启动原因</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点模块 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>入网次数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>代理变更次数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最近一次入网时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最近一次离网时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

a）相位：bit 0:A 相位（0：不是 A 相位，1：在 A 相位）Bit1：B 相位，Bit2：C 相位。

b) 网络状态：0：离网；1：入网。

c) 载波通道接收质量：接收代理站点载波信号 RSSI;信号质量信息长度为 8 比特，信号质量映射关系为： $ RSSI<-110\ dBm $ 时，量化值=0， $ RSSI\geq-110\ dBm $ 时，量化值= $ RSSI+111 $

d) 无线通道接收质量：接收代理站点无线信号 RSSI;信号质量信息长度为 8 比特，信号质量映射关系为： $ RSSI<-110\ dBm $ 时，量化值=0， $ RSSI\geq-110\ dBm $ 时，量化值= $ RSSI+111 $

e）系统启动原因：0：正常启动；1：断电重启；2：看门狗复位；3：程序异常复位。

f) 节点模块 ID：从节点设备监听到的某个邻居网络 CCO 模块的地址，6 字节。

g) 入网次数：最近 24 小时入网次数；

h) 代理变更次数：最近 24 小时变更代理次数；

i) 最近一次入网时间：年/月/日/时/分/秒

j) 最近一次离网时间：年/月/日/时/分/秒

### E8 00 03 6F：返回查询主节点运行信息

数据标识内容格式见下表。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>累计运行时间</td><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>节点从上电运行到现在的时间，单位：秒。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点模块ID</td><td style='text-align: center; word-wrap: break-word;'>11</td><td style='text-align: center; word-wrap: break-word;'>默认全0xff</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>发现站点数最大的站点</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>见心跳消息同字段定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大的发现站点数</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>见心跳消息同字段定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>系统启动原因</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0：正常启动；1：断电重启；2：看门狗复位；3：程序异常复位。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本地邻居网络个数</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>主站点可以监听到的邻居网络个数。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1#邻居网络标识号</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>邻居网络标识号SNID</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1#邻居网络CCO地址</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>邻居网络主站点地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1#邻居网络HPLC通道通信质量</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>HPLC通道RSSI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>............</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

a）累计运行时间：节点从上电运行到现在的时间，单位：秒。

b) 节点模块 ID: 默认全 0xff。

c） 发现站点数最大的站点：见心跳消息同字段定义。

d) 最大的发现站点数：见心跳消息同字段定义。

e）系统启动原因：0：正常启动；1：断电重启；2：看门狗复位；3：程序异常复位。

f) 本地邻居网络个数：主站点可以监听到的邻居网络个数。

g) 邻居网络标识号：邻居网络标识号 SNID。

h) 邻居网络 CCO 地址：邻居网络主站点地址。

i) 邻居网络 HPLC 通道通信质量：HPLC 通道 RSSI。

### E8 04 03 70: 返回节点自检信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 71 返回节点自检信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>过零自检结果</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>串口/485 不通状态</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上次离网原因</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>复位原因</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>





a）当从节点为三相表模块时，取值 0：未知；1：三相相序为 ABC；2：三相相序错误；3：存在断相；4：存在相同相位；当节点为单相表模块时，0：不支持过零；1：支持过零。

b) 串口/485不通状态：0：正常；1：历史上出现过不通现象；2：目前不通。

c）上次离网原因：0：未知；1：组网序列号变化；2：2个路由周期收不到信标帧；3：与代理节点连续四个路由周期的通信成功率都是0；4：站点所在层级超过15级；5：收到离线指示；0x80-0xEF:厂家自定义；0xF0-0xFF：保留。

d）复位原因：0：掉电复位；1：复位引脚复位；2：升级完成复位；3：CCO 控制从节点重启；0x80-0xEF:厂家自定义；0xF0-0xFF:保留。

e）注：如果 CCO 发送 PLC 报文查询 STA 的自检信息，没有收到应答，则回复集中器否认，原因为通信超时。

##### E8 00 03 72: 查询配置踢出后不允许入网时间

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>踢出不允许入网时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a) 单位：秒；

##### E8 04 03 74：返回查询运行参数信息

<div style="text-align: center;"><div style="text-align: center;">数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行参数总数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行参数ID1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数1配置数据长度</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>1字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数1数据</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见运行参数列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>运行参数ID2</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数2配置数据长度</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>1字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数2数据</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见运行参数列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>o 。o 。o 。</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">运行参数列表</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>运行参数ID</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x01</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>从节点RF发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x02</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>从节点PLC发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x03</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>异常离网锁定时间，单位：分钟，默认30分钟</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x04</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>RF通道控制开关：0：关闭；1：开启；默认开启</td></tr></table>

##### E8 00 03 90: 返回宽带载波频段

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 72 返回宽带载波频段数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>宽带载波频段</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

频段：0:1.953～11.96MHz；1：2.441～5.615 MHz；2：0.781～2.930 MHz；3～255表示保留

#### E8 00 03 91：返回多网络信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 73 返回多网络信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>多网络节点总数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本节点网络标识号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本节点主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络 1 标识号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络 1 主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网间 SNR</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居节点 n 网络标识号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>邻居网络 n 主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>网间 SNR</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 网间 SNR：节点与周边其他网络主节点 m 之间的信噪比，单位为 dB，取值范围（符号数）：-20~80；

### E8 00 03 93: 返回查询白名单生效信息

上行数据内容如下表。

<div style="text-align: center;"><div style="text-align: center;">表 74 返回查询白名单生效信息</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单开关</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单生效范围</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a） 白名单开关：0：关闭；1：打开；

b) 白名单生效范围：0：表档案；1：厂家自定义；2：表档案和厂家自定义的合集；3～255：保留。

数据标识内容格式见下表。

##### E8 00 03 95: 返回并发数

<div style="text-align: center;"><div style="text-align: center;">表 75 返回并发数数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>并发数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

#### E8 04 03 96: 返回查询设备类型

### 表 76 返回并发数数据标识内容格式



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 0 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 0 设备类型</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 0 离线时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 n-1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 n-1 设备类型</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 n-1 离线时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr></table>

a） 节点序号从 0 开始，其中 0 为主节点，后续为从节点；

b) 设备类型（来自低压电力线宽带载波通信规约第5部分：数据链路层通信协议6.4.1.4设备类型）

c）节点离线时长：从节点最后一次离线时长，单位为秒。



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x1</td><td style='text-align: center; word-wrap: break-word;'>抄控器</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x2</td><td style='text-align: center; word-wrap: break-word;'>集中器通信模块</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x3</td><td style='text-align: center; word-wrap: break-word;'>单相电表通信模块</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x4</td><td style='text-align: center; word-wrap: break-word;'>中继器</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x7</td><td style='text-align: center; word-wrap: break-word;'>三相表通信模块</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>其他值</td><td style='text-align: center; word-wrap: break-word;'>保留</td></tr></table>

##### E8 00 03 97: 返回台区组网成功率

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 77 返回台区组网成功率数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>台区组网成功率</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

注：模块上报扩大100倍，如组网成功率为100%，上报信息为10000。

<div style="text-align: center;"><div style="text-align: center;">E8 04 03 98: 返回节点信道信息</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本节点标识 TEI</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本节点 的代理节点标识（TEI）</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点 1 信道信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>16</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点 n 信道信息</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>16</td></tr></table>

识

还无法匹

周边节点信道信息，见下表。

<div style="text-align: center;"><div style="text-align: center;">表 78 节点信道信息数据单元格式</div> </div>


删除[狼 3]: 网络拓扑



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 m 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 m 标识（TEI）</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 m 的代理节点标识（TEI）</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 m 层级</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>下行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上下行通信成功率</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>信噪比</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>衰减</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 节点地址：节点入网的 MAC 地址；

b) 节点标识：D11~D0：定义为本站点的节点标识（TEI），最大不超过 1024；D13D12：定义为模块类型：0：HPLC 模块；1：双模模块；2：高速无线模块，D15D14：定义为邻居节点 m 与查询节点间信息通道类型：0：载波通道，1：无线通道；

c) 代理节点标识：本站点的代理站点节点标识（TEI）；

d) 节点层级：站点的网络层级，0 级代表 0 层级，以此类推；

e) 上行通信成功率：节点与周边节点 m 之间的上行通信成功率；

f) 下行通信成功率：节点与周边节点 m 之间的下行通信成功率；

g) 上下行通信成功率：节点与周边节点 m 之间的上下行通信成功率；

h）信噪比：节点与周边节点 m 之间的信噪比，单位为 dB ，取值范围（符号数）： $ -20^{\sim}80 $;

i）衰减：节点与周边节点 m 之间的衰减，单位为 dB，取值范围（无符号数）：0~150。

#### 6.8.5 写参数（AFN=04H）

### 数据标识编码定义

数据标识编码定义见下表。

设置格式[狼3]：段落间距段前：6磅，段后：6磅，编号+级别：1+编号样式：a，b，c，…+起始编号：1+对齐方式：左侧+对齐位置：7.4毫米+缩进位置：14.8毫米

设置格式[狼3]：项目符号和编号

删除[狼 3]：本站点的节点标识（TEI），最大不超过 1024；

删除[狼 3]:

<div style="text-align: center;"><div style="text-align: center;">表 79 写参数数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>设置主节点地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>添加从节点</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>删除从节点</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>允许/禁止从节点上报</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>激活从节点主动注册</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>终止从节点主动注册</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>添加从节点通信地址映射表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>6A</td><td style='text-align: center; word-wrap: break-word;'>设置最大网络规模</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>6B</td><td style='text-align: center; word-wrap: break-word;'>设置网络最大级数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>6C</td><td style='text-align: center; word-wrap: break-word;'>允许/禁止拒绝从节点信息上报</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>6D</td><td style='text-align: center; word-wrap: break-word;'>设置无线参数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>72</td><td style='text-align: center; word-wrap: break-word;'>配置踢出后不允许入网时间</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>74</td><td style='text-align: center; word-wrap: break-word;'>配置运行参数信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>80</td><td style='text-align: center; word-wrap: break-word;'>启动台区识别</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>81</td><td style='text-align: center; word-wrap: break-word;'>停止台区识别</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>90</td><td style='text-align: center; word-wrap: break-word;'>设置宽带载波频段</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>93</td><td style='text-align: center; word-wrap: break-word;'>允许/禁止白名单功能</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>F0</td><td style='text-align: center; word-wrap: break-word;'>重启节点</td></tr></table>

#### 下行报文

##### 数据标识内容定义

##### E8 02 04 01：设置主节点地址

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 80 设置主节点地址数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

##### E8 02 04 02: 添加从节点

数据标识内容格式下表。

该命令只用于添加表地址为 6 字节的电能表。

<div style="text-align: center;"><div style="text-align: center;">表 81 添加从节点数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点的数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

##### E8 02 04 03: 删除从节点

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 82 删除从节点数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点的数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

##### E8 02 04 04: 允许/禁止上报从节点事件

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 83 允许/禁止上报从节点事件数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>事件上报状态标志</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

事件上报状态标志：0 禁止，1 允许。该标识含义为是否允许从节点事件上报，上电后默认为允许，禁止后，电能表端的事件不再上报给集中器，且在下次下发允许或初始化前一直保持在禁止状态。

##### E8 02 04 05: 激活从节点主动注册

无数据标识内容。集中器激活从节点主动注册，要求主模块收集从模块下接电能表信息并上报集中器。主模块使用 E8 05 05 03 上报从节点信息。

删除[狼 3]:

##### E8 02 04 06: 终止从节点主动注册

无数据标识内容。

##### E8 02 04 07：添加从节点通信地址映射表

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 84 添加从节点通信地址映射表数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次添加从节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 通信地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 表计地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>12</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 通信地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 表计地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>12</td></tr></table>

注：每个从节点通信映射地址（18 字节）组成：通信地址（6 字节）+00 00 00 00 00 00H（6 字节）+表地址（6 字节）。

##### E8 02 04 6A：设置最大网络规模

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大网络规模</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a) 最大网络规模： $ \leq 1000 $；缺省配置：1000；

##### E8 02 04 6B：设置最大网络级数

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大网络级数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a) 最大网络级数： $ \leq 15 $；缺省配置：15；

##### E8 02 04 6C：允许/禁止拒绝从节点信息上报

数据标识内容格式见下表

设置格式[狼3]：缩进: 左 2.01 字符, 首行缩进: 0 字符, 编号 + 级别: 1 + 编号样式: a, b, c, ... + 起始编号: 1 + 对齐方式: 左侧 + 对齐位置: 7.4 毫米 + 缩进位置: 14.8 毫米



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>拒绝从节点信息上报使能</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

设置格式[狼 3]: 项目符号和编号

a） 拒绝从节点信息上报：0：禁止；1：允许；缺省配置：1；

删除[狼 3]: 规模

##### E8 02 04 6D: 设置无线参数

删除[狼 3]:

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>OPTION</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CHANNEL</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) OPTION: 0: OPTION1; 1: OPTION2; 2: OPTION3;

##### E8 02 04 72: 配置踢出后不允许入网时间

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>踢出不允许入网时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a) 单位：秒；缺省配置：CCO 自动动态控制；

##### E8 02 04 74: 配置运行参数

数据标识内容格式见下表



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点 MAC 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>配置参数总数 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 1ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 1 配置数据长度</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 1 数据</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见运行参数列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 2ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 2 配置数据长度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 2 数据</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>见运行参数列表</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>...</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 mID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 m 配置数据长度</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>1 字节</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>参数 m 数据</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见运行参数列表</td></tr></table>

<div style="text-align: center;"><div style="text-align: center;">运行参数列表</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>运行参数 ID</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x01</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>从节点RF发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x02</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>从节点PLC发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x03</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>异常离网锁定时间，单位：分钟，默认30分钟</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0x04</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>RF通道控制开关：0：关闭；1：开启；默认开启</td></tr></table>

#### E8 02 04 80: 启动台区识别

数据标识内容格式如表18所示。

<div style="text-align: center;"><div style="text-align: center;">表 85 启动台区识别数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>台区特征发送时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a）台区特征发送时长，表示 CCO 发送台区特征允许的最大时长，单位为分钟（最大不超过 1440 分钟）。0 代表 1440 分钟；超时时间到期后，台区识别自动结束。

注：若集中器未给 CCO 设置主节点地址，启动台区识别时，CCO 应答否认帧，否认原因码扩展为 EOH，主节点地址不存在。

##### E8 02 04 81：停止台区识别

无数据标识内容。

#### E8 02 04 90: 设置宽带载波频段

数据标识内容格式下表。

<div style="text-align: center;"><div style="text-align: center;">表 86 设置宽带载波频段数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>宽带载波频段</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 宽带载波频段：0:1.953～11.96MHz；1：2.441～5.615 MHz；2：0.781～2.930 MHz；3～255 表示保留。 $ \underline{\text{缺省配置：2；}} $

b）只能集中器使用，抄控器不能使用该命令。

<div style="text-align: center;"><div style="text-align: center;">E8 02 04 93：允许/禁止白名单功能</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单开关</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单生效范围</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 白名单开关：0：关闭；1：打开；缺省配置：1；

b) 白名单生效范围：0：表档案；1：厂家自定义；2：表档案和厂家自定义的合集；3～255：保留。

##### E8 02 04 F0: 重启节点

数据标识内容格式下表。

<div style="text-align: center;"><div style="text-align: center;">表 87 重启节点数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>等待时长</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a) 节点地址：CCO 可填全 0。

b）等待时长：节点重启前的等待时长，设置范围为 5~300，单位为秒。上行报文

写参数上行报文为确认/否认报文，详见“确认/否认”报文格式。

#### 6.8.6 上报信息（AFN=05H）

### 数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 88 上报信息数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>上报任务数据</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>上报从节点事件</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>上报从节点信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>上报从节点主动注册结束</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>上报任务状态</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>上报电能表数据</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'>80</td><td style='text-align: center; word-wrap: break-word;'>上报非本台区从节点信息</td></tr></table>

上行报文

数据标识内容定义

E8 05 05 01：上报任务数据

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 89 上报任务数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度 L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>

a）任务ID：用于区分不同任务的任务标识，每一个抄表任务对应一块表的一个数据项。

b）报文长度 L：通信协议的原始报文数据总长度，DLMS 为 2 字节长度报文。

c) 报文内容：通信协议的原始报文数据。

#### E8 05 05 02: 上报从节点事件

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 90 上报从节点事件数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度 L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>

a）报文长度 L：通信协议的状态字原始报文数据总长度。

b) 报文内容：通信协议的状态字原始报文数据。

### 1) 停电上报

报文内容：节点停电信息，定义如下：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>停上电事件类型</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>A0</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>A5</td><td style='text-align: center; word-wrap: break-word;'>A0</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>A5</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>A0</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>A5</td></tr></table>

(1) 停电事件类型：0x81—停电；0x82—上电；其他保留。

(2) 类型：0x00: 电表；其他保留；

(3) A0~A5: 电表地址。

注：每一帧上报报文都需要做到可独立解析。

### 2）拒绝从节点信息上报

报文内容：拒绝从节点信息，定义如下：



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>事件类型</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>A0</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>A5</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>A0</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>A5</td><td style='text-align: center; word-wrap: break-word;'>类型</td><td style='text-align: center; word-wrap: break-word;'>A0</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>A5</td></tr></table>

(1) 事件类型：0xA1：被拒绝从节点信息上报事件。

(2) 类型：0x00：单相模块；0x01：三相模块；

(3) A0~A5: 电表地址。

#### E8 05 05 03：上报从节点信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 91 上报从节点信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>上报从节点的数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'>……</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点 n 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>





上报从节点的数量  $ n \geqslant 1 $。

#### E8 05 05 04: 上报从节点主动注册结束

无数据标识内容。

#### E8 05 05 05：上报任务状态

数据标识内容格式见下表。

任务执行失败或成功时使用该命令上报。

<div style="text-align: center;"><div style="text-align: center;">表 92 上报任务失败数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>任务状态</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 任务 ID：区分不同任务的任务标识。

b) 从节点地址：失败从节点的地址。

c）任务状态：0 为成功，1 为从节点无响应，2 为数据不合法，FF 为其他错误。

#### E8 05 05 06: 上报电能表数据

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 93 上报电能表数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文长度 L</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>L</td></tr></table>

a）报文长度L：通信协议的状态字原始报文数据总长度。

b) 报文内容：通信协议的状态字原始报文数据。

#### E8 05 05 80：上报非本台区从节点信息

数据标识内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 94 上报非本台区从节点信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点设备类型</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点下接电表数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>应属台区主节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>报文内容</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

a) 从节点地址：当从节点设备类型为 01H 电表时，表示电表地址；

b) 从节点设备类型：01H 电表。

c） 所属台区主节点地址，表示该从节点应当归属的台区主节点地址。若无法确定台区归属（但明确不属于当前台区），填 6 个字节 FFH；

d) 报文内容：内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 95 报文内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>电表地址 1</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>电表地址 2</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>……</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>电表地址 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

##### 下行报文

下行报文为确认/否认报文，详见“确认/否认”报文格式。

#### 6.8.7 请求信息（AFN=06H）

数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 96 请求信息标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>06</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'>请求集中器时间</td></tr></table>

上行报文

数据标识内容定义

E8 06 06 01：请求集中器时间

无数据标识内容。

下行报文

数据标识内容定义

E8 06 06 01：请求集中器时间

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 97 请求集中器时间数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前时间—秒</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前时间—分</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前时间—时</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前时间—日</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前时间—月</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>当前时间—年（低字节）</td><td style='text-align: center; word-wrap: break-word;'>BCD</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

#### 6.8.8 传输文件（AFN=07H）

数据标识编码定义

数据标识编码定义见下表。

<div style="text-align: center;"><div style="text-align: center;">表 98 传输文件数据标识编码定义</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td colspan="4">数据标识编码</td><td rowspan="2">名称及说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>DI3</td><td style='text-align: center; word-wrap: break-word;'>DI2</td><td style='text-align: center; word-wrap: break-word;'>DI1</td><td style='text-align: center; word-wrap: break-word;'>DIO</td></tr></table>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>01</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>启动文件传输</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>02</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>传输文件内容</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>查询文件信息</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>00</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>查询文件处理进度</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>03</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>查询文件处理失败节点</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>E8</td><td style='text-align: center; word-wrap: break-word;'>04</td><td style='text-align: center; word-wrap: break-word;'>07</td><td style='text-align: center; word-wrap: break-word;'>05</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>返回查询文件处理失败节点</td></tr></table>

下行报文

数据标识内容定义

#### E8 02 07 01：启动文件传输

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 99 启动文件传输数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件性质</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>目的地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件总段数 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件大小</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件总校验</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件传输超时时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

a) 文件性质；

1）00H：清除下装文件；文件 ID 为 FFH 时，表示清除模块所有已接收且可以被清除的文件。文件 ID 不为 FFH 时，表示清除指定文件 ID 的文件，且该文件可以被清除。

2）01H：集中器本地通信模块文件；

3）02H：从节点模块文件；

b) 文件 ID：用来区分不同的文件。

c)

d) 文件总段数 n：文件传输内容的总段数。

e) 文件大小：文件的总长度，单位字节。

f）文件总校验：文件所有内容的 CRC16 校验和。CRC16 校验生成多项式采用 CRC16-CCITT（0x1021）， $ x_{16} + x_{12} + x_{5} + 1 $。

g) 文件传输超时时间：模块如果无法在超时时间内完成文件传输，则不再向从模块传输文件。集中器查询文件处理进度时，模块返回未全部成功，存在失败节点。单位为分钟。

h) 文件传输采用串行方式，不允许并行传输文件。模块可根据自身存储容量存储多个文件。模块在未接收完文件时，若该文件不存在或者可以清除，则回复确认；若无法删除则回复否认。

#### E8 02 07 02: 传输文件内容

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 100 传输文件内容数据标识内容格式</div> </div>




<table border="1" style="margin: auto; word-wrap: break-word;"><tr><td style="text-align: center; word-wrap: break-word;">数据标识内容</td><td style="text-align: center; word-wrap: break-word;">数据格式</td><td style="text-align: center; word-wrap: break-word;">字节数</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段号</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段长度 L</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段内容</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">L</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段校验</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr></table>




a） 文件段号：文件内容的传输帧序号，取值范围 0 至 n-1（n 为文件总段数）

b) 文件段长度 L：该帧文件内容长度；文件段长度不大于模块所支持的最大长度，长度值应在 64、128、256、512、1024 中选择。除了最后一个文件段，其他文件段的长度必须相同。

c) 文件段内容：该帧传输的文件内容，长度为 L 字节。

d）文件段校验：该帧文件内容的 CRC16 校验和。CRC16 校验生成多项式采用 CRC16-CCITT  $ (0x1021) $， $ x^{16} + x^{12} + x^{5} + 1 $。

##### E8 00 07 03: 查询文件信息

无数据标识内容。

E8 00 07 04: 查询文件处理进度

无数据标识内容。

### E8 03 07 05: 查询文件传输失败节点

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 101 查询文件传输失败节点数据单元格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次查询的节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>

起始序号从 0 开始。

#### 上行报文

#### 数据标识内容定义

E8 02 07 01：启动文件传输

上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

E8 02 07 02: 传输文件内容

上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。

### E8 00 07 03: 查询文件信息

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 102 查询文件信息数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件性质</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>目的地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件总段数 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件大小</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>4</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件总校验</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>已成功接收文件段数 m</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a) 文件性质:

1) 00H: 清除下装文件;

2）01H：本地通信模块文件；

3）02H：从节点模块文件；

b) 文件 ID：用来区分不同的文件。

c) 目的地址：文件传输的目的地址，99 99 99 99 99 99 为广播地址。

d) 文件总段数 n：文件传输内容的总帧数。

e) 文件大小：文件的总长度，单位字节。

f）文件总校验：文件所有内容的 CRC16 校验和。

g）成功接收文件段数：文件接收方已经成功接收到的文件段数，范围为1~n。n为文件总段数。如果为0表示尚未开始传输，为n表示传输已完成，为m表示段号0~m-1的帧已传输完成，可以从段号为m的帧开始续传。

#### E8 00 07 04: 查询文件处理进度

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 103 查询文件处理进度数据标识内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据标识内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>文件处理进度</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>处理未完成的文件 ID</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>失败的节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>

a）文件处理进度：0 全部成功，可以接收新文件；1 正在处理，不能接收新文件；2 未全部成功，存在失败节点。

b) 处理未完成的文件 ID：当文件处理进度为 1—正在处理或 2—未全部成功时有效，表示当前处理未完成的文件 ID。

c） 失败的节点数量：当文件处理进度为 2-处理未全部成功时有效，表示失败的节点数量。

#### E8 04 07 05：返回查询文件传输失败节点

数据标识内容格式见下表。

<div style="text-align: center;"><div style="text-align: center;">表 104 返回查询文件传输失败节点数据单元格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点总数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本次应答的节点数量 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点 1 地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td><td style='text-align: center; word-wrap: break-word;'>......</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节地址 n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>

#### 维护模块（AFN=FOH）

该功能的具体内容由厂家自定义，用于模块维护、调试和测试。

# 附录 A 集中器与本地通信模块交互流程

# (规范性附录)

### A. 1 模块识别流程

设置格式[狼3]: 2级

模块识别流程在如下场景时启动：

1. 集中器和模块初始化上电；

2. 集中器发现异常复位模块；

3. 模块发现异常主动复位；

4. 模块热插拔。

集中器复位模块的时间不得少于 200ms，模块复位后应当主动上报 “本地通信模块运行模式信息”，模块识别流程说明如下：

a）集中器读取 MID（模块识别引脚）引脚状态，判断模块是否在位；如果引脚为低电平，说明模块在位，进入 b）步骤；

b) 集中器进行波特率自适应，匹配模块的串口通信速率。集中器可通过“查询本地通信模块运行模式信息”匹配通信速率；

c) 若查询失败，集中器等待模块上报“本地通信模块运行模式信息”，等待时间 1min。超时则主动下发查询“本地通信模块运行模式信息”命令，每次主动查询间隔 20 秒，如果 3 次之后仍然查询失败，则集中器复位模块进入步骤 b）。若集中器 3 次复位模块仍不成功，则模块识别流程结束。如果集中器成功获取到“本地通信模块运行模式信息”，则进入步骤 4）；

d) 集中器根据“本地通信模块运行模式信息”进行判断，如果本地通信模块上报的主节点地址与集中器不匹配，则认为该模块是新装模块，下发“初始化档案”和“初始化任务”。初始化完毕，下发“设置主节点地址”命令，并通过“查询主节点地址”命令验证。

e) 集中器与本地模块主节点地址一致后，开始档案同步流程和任务执行流程。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//45c783da-e990-4bfb-af75-7895e289df36/markdown_2/imgs/img_in_image_box_275_914_977_1467.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A48Z%2F-1%2F%2F817ed20b78bb0d0197721ea91c31fdba16be24f497def0566a5428d5b16b3d12" alt="Image" width="43%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 A.1 模块识别流程图</div> </div>


#### A. 2 档案同步流程

档案同步流程过程说明如下：

a） 集中器下发“查询从节点数量”命令（AFN=03H-DI=E8 00 03 05）查询从节点数量；

b) 获得从节点数量后，集中器下发“查询从节点信息”命令（AFN=03H-DI=E8 03 03 06）获取从节点信息；

c） 集中器将模块的“返回查询从节点信息”（AFN=03H-DI=E8 04 03 06）与集中器上保存的节点信息比较，如果不一致，则可按需依次“删除从节点”（AFN=04H-DI=E8 02 04 03）或者“初始化档案”（AFN=01H-DI=E8 02 01 02）删除全部从节点，然后通过“添加从节点”（AFN=04H-DI=E8 02 04 02）添加；

d） 操作完成后，返回 2)“查询从节点信息”，直到集中器与模块档案一致；

e) 确认档案一致后，按需“初始化任务”（AFN=01H-DI=E8 02 01 03）清空全部任务，此后，集中器可下发任务进行抄表。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//45c783da-e990-4bfb-af75-7895e289df36/markdown_3/imgs/img_in_image_box_420_532_892_1071.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A48Z%2F-1%2F%2Fa5e9020fbea534a5d949312e7f62510dd8397f02edf18f96aa062fd90c63d46a" alt="Image" width="29%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 A.2 档案同步流程图</div> </div>


### A. 3 任务执行流程

任务执行流程用于转发数据，进行抄表，说明如下：

a）模块默认处于任务暂停状态，集中器按需下发“启动任务”（AFN=02H-DI=E8 02 02 08）。

b） 集中器下发“添加任务”（AFN=02H-DI=E8 02 02 01），需要指定任务的优先级以及任务 ID。一个任务抄读一块表的一个数据项，地址域中指定目标地址。

c) 集中器模块需要缓存任务，集中器可“查询剩余可分配任务数”（AFN=02H-DI=E8 00 02 05），模块默认能缓存 50 个任务，典型任务的数据长度为 400 字节。

d） 集中器模块收到各任务后，不必等待所有任务全部下发，可以自行组织各任务发送顺序。

e）集中器负责指定任务的优先级。每当模块收到一个新任务，模块要保证高优先级的任务能得到优先执行。

f) 集中器每隔一段时间需查询集中器模块的建议超时时间，动态调整添加任务时的超时时间。删除[狼 3]: 要求

删除[狼3]: 至少

删除[狼 3]: 10

删除[狼 3]: 24

g）集中器负责管理任务执行的时间和周期，任务由集中器下发到模块后，模块按当前缓存任务的优先级执行。任务是否超时由集中器判断，集中器判断任务超时后，按需重新下发任务。

h) 对于有数据返回的任务，从节点数据成功返回主模块后，模块向集中器“上报任务数据”（AFN=05-DI=E8 05 05 01），集中器返回确认帧；如果主模块没有成功接收从节点的返回数据，则向集中器“上报任务状态”失败，集中器返回确认帧。对于没有数据返回的任务，任务发送完成后，模块向集中器“上报任务状态”（AFN=05-DI=E8 05 05 05）成功，集中器返回确认帧，任务发送失败，则模块向集中器“上报任务状态”（AFN=05-DI=E8 05 05 05）失败，集中器返回确认帧。删除

i）当需要立即执行任务时，可以先“暂停任务”（AFN=02H-DI=E8 02 02 09），再通过“添加任务”（AFN=02H-DI=E8 02 02 01）增加高优先级的任务，然后再“启动任务”（AFN=02H-DI=E8 02 02 08）。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//45c783da-e990-4bfb-af75-7895e289df36/markdown_4/imgs/img_in_image_box_330_495_939_953.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A49Z%2F-1%2F%2F55a5ce6353bf1cc22cfb680a64f3677881d70ac61882fdbf1eba093a12020e24" alt="Image" width="37%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 A.3 任务执行流程图</div> </div>


#### A. 4 容错机制流程

为提高集中器与本地模块通信的鲁棒性，引入如下的容错机制。

a）集中器与模块无报文交互时间超过15分钟时，需向模块发送“查询未完成任务数”命令（AFN=02H-DI=E8 00 02 03）。如果模块无响应，则等待20s后重新查询。

b）如果集中器连续三次查询模块仍无响应，则硬件复位模块，启动模块识别流程。

c） 如果模块返回了“未完成任务数”（AFN=02H-DI=E8 02 02 03），集中器判断模块任务数是否与集中器的任务数一致，不一致则通过“初始化任务”或“删除任务”删除全部或部分任务，再通过“添加任务”（AFN=02H-DI=E8 02 02 01）保证集中器与模块任务的一致性。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//fa85b8f8-933a-4d52-81ed-928af719d9c2/markdown_0/imgs/img_in_image_box_432_164_820_817.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A26Z%2F-1%2F%2F1f97b916381ee6bbb7572dde479e1904fd251d3a8d7d64c96fa9875c7f7c6a73" alt="Image" width="24%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 A.4 容错机制流程图</div> </div>


### A. 5 从节点主动注册流程

a）从节点主动注册流程用于自动搜表，过程说明如下：

b) 集中器下发“激活从节点主动注册”（AFN=04H-DI=E8 02 04 05）；

c）模块向集中器上报“上报从节点信息”（AFN=05H-DI=E8 05 05 03），集中器保存处理上报信息并确认，重复步骤 b；

d）集中器超过10分钟未收到“上报从节点信息”时，则“查询从节点主动注册进度”（AFN=03H-DI=E8 00 03 08），如果返回查询结果为从节点已停止主动注册，则下发“终止从节点主动注册”（AFN=04H-DI=E8 02 04 06）；如果返回查询结果为从节点正在主动注册，继续执行步骤b）。如果空闲时间超过30分钟则下发“终止从节点主动注册”。

e）如果集中器收到模块“上报从节点主动注册结束”（AFN=05H-DI=E8 05 05 05），则回复确认帧，并下发“终止从节点主动注册”（AFN=04H-DI=E8 02 04 06）；

f) 集中器根据上报节点信息，按需进行档案同步。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//fa85b8f8-933a-4d52-81ed-928af719d9c2/markdown_1/imgs/img_in_image_box_291_157_933_834.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A27Z%2F-1%2F%2F597019e0afa5d11884826acee4fcae490caddc4e02e181190a6c39ab2ef37968" alt="Image" width="39%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 A.5 从节点主动注册流程图</div> </div>


### A.6 文件传输流程

文件传输流程用于远程升级等场景，过程说明如下：

a） 集中器根据当前状态判断是新启动传输还是继续上一次传输；

b）如果是继续上一次传输，先“查询文件信息”（AFN=07H-DI=E8 03 07 03）；如果查询到的文件信息与集中器一致，已经传输了 m 段（第 0 至第 m-1 段），则“传输文件内容”（AFN=07H-DI=E802 07 02），从第 m 段开始传输。

c) 如果需要新启动传输，或者模块与集中器文件信息不匹配，则要“启动文件传输”（AFN=07H-DI=E8 02 07 01）开始一轮新的传输。并下发“传输文件内容”（AFN=07H-DI=E8 02 07 02），从第 0 段开始传输。

d) 继续传输直到第 n-1 段（总段数为 n）文件完成。

<div style="text-align: center;"><img src="https://pplines-online.bj.bcebos.com/deploy/official/paddleocr/pp-ocr-vl-15//fa85b8f8-933a-4d52-81ed-928af719d9c2/markdown_2/imgs/img_in_image_box_417_149_895_667.jpg?authorization=bce-auth-v1%2FALTAKzReLNvew3ySINYJ0fuAMN%2F2026-04-17T08%3A46%3A28Z%2F-1%2F%2F2f0b9a8fa8474ccdbaf7b93111a7ce396efd9e76e4cdccc46d4bdf36d4935717" alt="Image" width="29%" /></div>


<div style="text-align: center;"><div style="text-align: center;">图 A.6 文件传输流程图</div> </div>


### A. 7 精准对时

精准对时指 STA 利用 NTB 对集中器下发的校时时间进行修正并转发。

### A. 7.1 业务描述

当 STA 与 CCO 完成组网之后，STA 和 CCO 维持 NTB 同步。当集中器发起精准对时任务时，集中器向 CCO 下发校时报文。CCO 收到后在报文前添加 NTB 及控制相关内容并转发给 STA。STA 接收到报文之后将其中的 NTB 与自身 NTB 对比以补偿传输延迟，之后下发给电表进行校准。

### A. 7.2 STA 模块设计任务

STA 模块相关的任务包括：

响应精准对时命令：STA 接收到 CCO 的校时报文后，解析报文内容，获得集中器时钟 Tc 和 CCO 网络基准时间 NTBc。利用 STA 当前网络基准时间 NTBs 更新时钟 Ts=Tc+（NTBs-NTBc）×NTB 间隔。其中，NTB 间隔为 1/25000000s（计数频率为 25MHz）。之后，替换校时报文中的时间字段，下发给电表进行校时。

### A. 7.3 CCO 模块设计任务

CCO 模块相关的任务包括：

精准对时命令执行：CCO 响应集中器的精准对时指令，当接收到指令时获取集中器时钟 Tc 并记录当前 CCO 网络基准时间 NTBc，组织宽带载波报文向 STA 发送精准对时指令。

### A.7.4 集中器设计任务

集中器与精准对时相关的任务包括：

广播校时：一般在每天凌晨过零点后的一个小时内，进行全台区广播校时命令的发起。

### A. 7.5 本地接口协议

本地接口协议见“添加任务”和“启动任务”报文格式介绍；

### A.7.6 宽带载波协议

精准对时帧类型如下表所示，见《PLUZ低压电力线宽带载波通信规约 第5部分：应用层通信协议》的数据转发部分，业务代码填写 01H。

<div style="text-align: center;"><div style="text-align: center;">表 105 精准对时帧类型</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>帧类型</td><td style='text-align: center; word-wrap: break-word;'>报文端口号</td><td style='text-align: center; word-wrap: break-word;'>业务标识</td><td style='text-align: center; word-wrap: break-word;'>描述</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>数据转发</td><td style='text-align: center; word-wrap: break-word;'>0x13</td><td style='text-align: center; word-wrap: break-word;'>0x01</td><td style='text-align: center; word-wrap: break-word;'>数据透传至模块</td></tr></table>

转发数据内容格式如下表所示。

<div style="text-align: center;"><div style="text-align: center;">表 106 精准对时转发数据内容格式</div> </div>




<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>域</td><td style='text-align: center; word-wrap: break-word;'>字节号</td><td style='text-align: center; word-wrap: break-word;'>比特位</td><td style='text-align: center; word-wrap: break-word;'>域大小（比特）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>端口号</td><td style='text-align: center; word-wrap: break-word;'>1-2</td><td style='text-align: center; word-wrap: break-word;'>0-15</td><td style='text-align: center; word-wrap: break-word;'>16</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>序号</td><td style='text-align: center; word-wrap: break-word;'>3</td><td style='text-align: center; word-wrap: break-word;'>0-7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>0-7</td><td style='text-align: center; word-wrap: break-word;'>8</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CCO 网络基准时间</td><td style='text-align: center; word-wrap: break-word;'>5-8</td><td style='text-align: center; word-wrap: break-word;'>0-31</td><td style='text-align: center; word-wrap: break-word;'>32</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>校时报文</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>

a）端口号：用于区分校时的通信技术。当前使用载波通信，填写01H。

b) 序号：CCO 下发广播报文的序号，从 1 开始编号。为提高成功率，CCO 可以针对集中器的一条校时命令发送多条校时报文（时间经 CCO 修正），该报文组序号相同，STA 重复接收到相同序号的校时报文时不做处理。

c) CCO 网络基准时间：CCO 当前 NTB。

d) 校时报文:

1) 报文格式:



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>起始字符（68H）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>地址域</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>起始字符（68H）</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>控制码 C</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>长度 L</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>数据域</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>校验和 CS</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>结束字符（16H）</td></tr></table>

2) 地址域：99999999999H;

3） 控制码：C=1FH;

4) 数据域长度：L = 0 CH;

5) 数据域内容:



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据项</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>取值范围</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>年高字节</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见 IEC62056-62</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>年低字节</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见 IEC62056-62</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>月</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1-12，其中最高位是夏令</td></tr><tr><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'>时标识位：0，非夏令时；1，夏令时；</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>日</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1-31</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>星期</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1-7</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>时</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>0-23</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>分</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>0-59</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>秒</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>0-59</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1/100 秒</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>0-99</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>偏差高字节</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见 IEC62056-62</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>偏差低字节</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见 IEC62056-62</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>时钟状态</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>见 IEC62056-62</td></tr></table>





##### 6) 校验和 CS

从帧起始符开始到校验码之前的所有各字节的模 256 的和，即各字节二进制算术和，不计超过 256 的溢出值。

### A. 8 停电上报

#### A. 8.1 业务描述

停电上报指在通信模块中安装超级电容，当电网发生停电事故时，通信模块仍可以工作一段时间，并向主站上报停电事件。

#### A. 8.2 STA 模块设计任务

a) STA 需加装超级电容，掉电后应可维持模块正常工作 60s 以上。停电事件发生时，停电 STA 以本地广播形式进行上报，未停电 STA 接收到广播报文后，收集 30s 的停电事件，以单播形式上报给 CCO，当收到 CCO 返回的确认帧后，不再上报重复事件。

b) STA 按照以下规则判断是否发生停电事件：若连续 50 个工频周期没有检测到过零信号且 12V 电压跌落到 9.5V 以下则判断为模块停电。此时模块应通过 VSS 管脚判断是电表停电还是模块拔出，当事件为电能表停电时需要进行上报，模块拔出时不上报事件。

#### A. 8.3 CCO 模块设计任务

CCO 模块接收到第一条停电上报消息后，以 5s 为单位汇总该时间段内的停电事件，上报给集中器。上报过的停电事件在 5min 内不再上报。对于停电 STA 的上报信息，CCO 在接收之后不作回复；对于未停电 STA 的上报消息，CCO 在接收到之后回复确认帧。

#### A. 8.4 集中器设计任务

集中器需要加装备用电源，掉电后应可维持模块正常工作 120 s 以上。集中器在接收到 CCO 的停电上报信息后，需要对数据进行处理，生成对应的电表停上电告警数据，并上报主站。

#### A. 9 相位识别及告知

#### A. 9.1 业务描述

相位识别指利用过零 NTB 信息判断各节点所处的相位，识别模式采用集中式识别。相位告知指 CCO 通过广播相线告知报文通知各在网站点相位识别的结果。

#### A. 9.2 STA 模块设计任务

STA 模块相关工作内容包括:

响应 CCO 发起的从节点过零 NTB 信息采集命令：执行 CCO 发起的过零 NTB 采集命令，采集自身的过零 NTB 数据，并将其上报给 CCO。

考虑到互联互通协议的兼容性，STA 需要支持数据链路层的过零 NTB 采集指示报文和相位特征采集指示命令。

### A. 9.3 CCO 模块设计任务

CCO 模块相关工作内容包括：

a) 发起从节点相位识别任务：CCO 在从节点入网后，发起针对入网从节点的过零 NTB 数据采集命令，并接收从节点发来的过零 NTB 信息。

b) 分析从节点的相位信息：CCO 将从节点的过零 NTB 信息和其自身的过零 NTB 信息进行比对，生成从节点的相位信息和零火线接线状态，并存储在本地。

c）响应集中器的从节点信息查询命令：CCO 收到集中器发来的从节点信息查询命令，将从节点的相位信息和零火接线状态上报给集中器。

考虑到互联互通协议的兼容性，CCO 需要支持下发数据链路层的过零 NTB 采集指示报文 和相位特征采集指示命令。

### A. 9.4 集中器设计任务

集中器相关工作内容包括：

a) 周期性从节点信息同步：集中器可以周期性查询 CCO 中的从节点信息，将相应报文中的从节点相位信息及零火线接线状态记录保存到本地数据库中。

b) 响应主站的相位信息查询：集中器接到主站的相位信息查询命令后，向主站上报下属电表的相位信息。

### A. 10 拒绝从节点信息上报

### A. 10.1 STA 模块设计任务

该功能，从节点STA不做特殊开发。

### A. 10.2 CCO 模块设计任务

主节点CCO，在组网完成后，对于新的入网请求，因不在白名单拒绝的信息，组织拒绝列表事件上报报文通知集中器。为避免 CCO 频繁上报拒绝列表事件，相同的从节点应当每六小时只允许上报一次（CCO 内过滤处理）。该功能 CCO 默认关闭，需要远程主站通过集中器下发命令给 CCO，使能该功能。见 “上报从节点事件” 报文。

### A. 10.3 集中器设计任务

集中器将该节点入网请求被拒绝的信息进行保存，通过上行协议上报主站或接受主站的查询命令。

### 附录 B 注意事项

### B.1 电表程序在线升级注意事项

集中器下发广播报文升级网络内所有电表：

集中器向CCO下发“添加任务”（AFN=02H-DI=E8 02 02 01）命令报文，其中“目的地址”为广播地址“0x999999999999”，表示向所有在网电表广播当前消息。集中器下发命令报文时，注意接收的对应上行确认/否认报文，如果是确认报文，则可以继续下发下一个任务命令，如果是否认报文，则表示CCO已经不能缓存更多任务，需要集中器适当等待。集中器可以通过下发“查询剩余可分配任务数”命令报文，确认是否可以继续下发任务报文。也可以通过接收到的“上报任务数据”（AFN=05-DI=E8 05 05 01）和“上报任务状态”（AFN=05-DI=E8 05 05 05）报文，来确认继续下发任务报文。

### B.2 激活从节点主动注册注意事项

 $ \underline{\text{集中器向CCO下发“激活从节点主动注册”命令报文，CCO开启主动注册业务期间，将自动默认白名单关闭。}} $

### B. 3 应用业务帧长度注意事项

本协议上下行应用业务帧长度限制：420字节；

### 删除[狼 3]:

设置格式[狼3]：缩进：左侧：0.1 毫米，首行缩进：6.9 毫米

设置格式[狼3]：正文，居中，缩进：首行缩进：0字符，段落间距段前：2行，段后：0.5行，字体对齐方式：自动对齐，对齐到网格，调整中文与数字的间距，调整中文与西文文字的间距，无孤行控制，1级，使用中文规则控制首尾字符，定义网格后自动调整右缩进

设置格式[狼3]：正文，缩进：首行缩进：0字符，段落间距段前：0.5行，段后：0.5行，行距：多倍行距0.91字行，字体对齐方式：自动对齐，对齐到网格，调整中文与数字的间距，调整中文与西文文字的间距，无孤行控制，2级，使用中文规则控制首尾字符，定义网格后自动调整右缩进

### 设置格式[狼3]: 正文

设置格式[狼3]：缩进：左 0.08 字符，首行缩进：1.91 字符

设置格式[狼3]：字体：（默认）宋体，（中文）宋体，字体颜色：黑色，紧缩量：0.3磅，英语（美国），（中文）中文（简体）

设置格式[狼3]：标准正文

设置格式[狼3]：字体：（默认）宋体，（中文）宋体，字体颜色：黑色，紧缩量：0.3磅，英语（美国），（中文）中文（简体）

### 设置格式[狼 3]: 标准正文

设置格式[狼3]：字体颜色：黑色，紧缩量：0.3磅，英语(美国)，（中文）中文(简体)

设置格式[狼3]：缩进：左 0.08 字符，首行缩进：1.91 字符

设置格式[狼 3]: 正文, 缩进: 首行缩进: 0 字符

设置格式[狼 3]：缩进：首行缩进：0 字符

