周期6到7：代理变更中；

周期8：接收到代理变更回复报文，代理变更成功。

代理评估失败示例如图63所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_229_290_997_462.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 63 代理评估失败示意图</div>


周期1到4：路径质量良好，不启动代理变更；

周期5：检测到路径质量变差，不满足通信要求，代理评估失败，不启动代理变更；

周期6：检测到路径质量变差，不满足通信要求，代理评估成功，启动代理变更；

周期7.8：代理变更中：

周期9：代理变更成功。

代理变更失败示例如图64所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_228_721_995_901.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 64 代理变更失败示意图</div>


周期1：路径变差，启动代理变更；

周期2.3：代理变更中：

周期4：代理变更超时，导致变更失败；

周期5到7：不满足变更间隔：

周期8：路径变差，启动代理变更；

周期8.9：代理变更中：

周期10：代理变更成功。

不满足变更间隔示例如图65所示。

<div style="text-align: center;"><img src="imgs/img_in_image_box_230_1224_995_1402.jpg" alt="Image" width="64%" /></div>


<div style="text-align: center;">图 65 不满足变更间隔示意图</div>


周期1：路径变差，启动代理变更；

周期2.3：代理变更中；