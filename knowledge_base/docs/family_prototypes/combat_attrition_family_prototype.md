# family prototype：combat_attrition

family 名称：`combat_attrition`

family 层级：主干 family（trunk）

scene：红蓝双方在交战过程中的兵力消耗与战损演化，通常基于兰彻斯特平方律或类似消耗模型。核心关注双方初始兵力、杀伤率系数、兵力曲线与对抗结果，不是目标跟踪估计，也不是战场覆盖与情报融合代理。

典型对象词：红蓝对抗、兵力消耗、战损、兰彻斯特、力量对比、杀伤率、交战演化。

关键槽位：`red0`、`blue0`、`alpha`、`beta`、`dt`、`stop_time`。

反混淆词：态势感知、预警、侦察覆盖、情报融合、目标跟踪、卡尔曼滤波、观测噪声、航迹、卫星轨道、火箭发射。

典型问法：
- 构建一个红蓝双方兵力消耗 MATLAB 模型，给定双方初始兵力和杀伤率系数。
- 做一个兰彻斯特平方律战损仿真，分析交战后兵力剩余。
- 生成战场对抗消耗脚本，输出红蓝兵力随时间变化曲线。
- build a combat attrition model with red force, blue force, and kill coefficients.

反混淆提示：
- 如果重点是“红蓝兵力、战损、消耗、兰彻斯特”，优先 `combat_attrition`。
- 如果重点是“覆盖度、情报供给、融合增益、预警图景”，更接近 `battlefield_awareness`。
- 如果重点是“单目标雷达跟踪、量测噪声、卡尔曼滤波”，更接近 `tracking_estimation`。
