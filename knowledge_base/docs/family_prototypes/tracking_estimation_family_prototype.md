# family prototype：tracking_estimation

family 名称：`tracking_estimation`

family 层级：主干 family（trunk）

scene：单传感器二维目标跟踪与状态估计，通常使用常速度模型和线性卡尔曼滤波。核心关注目标位置速度估计、观测噪声、过程噪声、量测轨迹与估计轨迹，不是战场层的态势融合，也不是红蓝兵力对抗消耗。

典型对象词：雷达目标跟踪、单目标跟踪、航迹跟踪、卡尔曼滤波、状态估计、量测轨迹、目标估计。

关键槽位：`measurement_noise`、`target_speed_x`、`target_speed_y`、`process_noise`、`steps`、`dt`、`x0`、`y0`。

反混淆词：态势感知、侦察覆盖、预警图景、情报融合、威胁评分、红蓝兵力、兵力消耗、兰彻斯特、齐射拦截。

典型问法：
- 生成一个雷达单目标卡尔曼跟踪 MATLAB 模型，给定观测噪声和过程噪声。
- 做一个二维航迹跟踪估计仿真，分析真实轨迹、量测轨迹和估计轨迹。
- 构建目标状态估计脚本，给定目标 x/y 方向速度和量测误差。
- build a single-target tracking model with Kalman filter, measurement noise, and process noise.

反混淆提示：
- 如果重点是“单目标、量测、滤波、估计误差、轨迹重建”，优先 `tracking_estimation`。
- 如果重点是“预警、侦察覆盖、多源情报融合、战场图景”，更接近 `battlefield_awareness`。
- 如果重点是“红蓝兵力损耗、杀伤率、对抗演化”，更接近 `combat_attrition`。
