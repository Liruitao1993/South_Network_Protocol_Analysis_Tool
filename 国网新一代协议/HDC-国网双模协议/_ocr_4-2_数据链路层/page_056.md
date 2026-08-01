表示申请代理变更站点的新代理站点的TEI。

## 51376 端到端序列号

表示端到端的报文序列号。请求代理变更的站点，在产生代理变更请求报文时，需要获取一个序列号，CCO在确认代理变更时，需要在代理变更请求确认报文中携带代理变更请求报文中的端到端报文序列号。

## 51377 路径序号

表示路径通知序列号。在代理变更请求确认报文中，会携带路由路径信息。每次代理变更请求确认报文的发送，CCO会获取一个路径通知序列号，获取的路径序列号是递加的。代理站点或者STA站点，在刷新路由表项时，需要判断路径序列号是否为最新的。

## 51378 位图大小

表示“子站点位图”字段的大小，单位是字节。

## 51379 子站点位图

采用位图表示代理变更请求发起站点的所有子站点的TEI×根据TEI大小在比特图中相应的位置上填写标志，当比特位的值为1时，表示对应的TEI有效。如第0字节的第1比特值为1，表示的TEI为1的站点为此次发起代理变更的站点的子站点；第1字节的第0比特值为1，表示的TEI为8的站点为此次发起代理变更的站点的子站点。

## 5138 离线指示报文

## 51381 离线指示报文格式

离线指示报文（MMeLeaveInd）格式的定义如表91所示。

<div style="text-align: center;">表 91 离线指示报文格式</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>字段</td><td style='text-align: center; word-wrap: break-word;'>字段大小(字节)</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>原因</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点总数</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>延迟时间</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>保留</td><td style='text-align: center; word-wrap: break-word;'>10</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>站点MAC地址</td><td style='text-align: center; word-wrap: break-word;'>L（可变长）</td></tr></table>

## 51382 原因

表示CCO告知站点需要离线的原因，定义如表92所示。

<div style="text-align: center;">表92 原因字段</div>



<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>值</td><td style='text-align: center; word-wrap: break-word;'>定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>0</td><td style='text-align: center; word-wrap: break-word;'>CCO 通知站点立即离线</td></tr></table>