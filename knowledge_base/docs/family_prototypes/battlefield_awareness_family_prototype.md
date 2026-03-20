# family prototype：battlefield_awareness

family 名称：`battlefield_awareness`

family 层级：扩展 family（作为主干 family 反混淆参照补充）

scene：战场层的覆盖度、侦察情报供给与态势感知融合，关注预警图景、侦察覆盖、信息刷新与感知水平演化。它不是单目标状态估计，也不是基于兵力损耗方程的红蓝消耗模型。

典型对象词：战场态势感知、预警、侦察覆盖、情报供给、战场图景、态势融合、感知水平。

关键槽位：`coverage0`、`feed0`、`decay_rate`、`fusion_gain`、`dt`、`stop_time`。

反混淆词：卡尔曼滤波、单目标跟踪、量测噪声、过程噪声、航迹估计、红蓝兵力、兰彻斯特、杀伤率、火箭发射、卫星轨道。

典型问法：
- 构建一个战场态势感知 MATLAB 模型，给定初始覆盖度和情报供给。
- 做一个预警与侦察覆盖融合仿真，分析态势感知水平随时间变化。
- 生成战场图景融合脚本，考虑覆盖衰减与信息融合增益。
- build a battlefield awareness model with sensor coverage, intel feed, and fusion gain.

反混淆提示：
- 如果重点是“单目标、航迹、卡尔曼、量测误差”，更接近 `tracking_estimation`。
- 如果重点是“红蓝兵力、杀伤系数、消耗曲线、战损”，更接近 `combat_attrition`。
- 如果用户只说“态势模型”，必须继续澄清是战场层感知融合，还是平台层跟踪估计，还是红蓝兵力对抗。
