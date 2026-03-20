# family prototype：underwater_launch

family 名称：`underwater_launch`

family 层级：主干 family（trunk）

scene：鱼雷或水下航行体在水下管内 / 出管过程中的一维发射动力学。核心关注推力、浮力、重力、水阻、排水体积与出管速度位移，不是空气中的火箭升空，也不是二维导弹飞行轨迹。

典型对象词：鱼雷、水下发射、潜艇、出管、管内发射、水下航行体、浮力、水阻。

关键槽位：`mass`、`thrust`、`displaced_volume`、`water_density`、`drag_coeff`、`area`、`dt`、`stop_time`。

反混淆词：火箭、运载火箭、垂直升空、空气阻力、发射角、二维弹道、卫星、轨道、卡尔曼跟踪、红蓝兵力。

典型问法：
- 构建一个鱼雷水下出管发射 MATLAB 模型，考虑浮力、水阻和推力。
- 做一个潜艇水下发射仿真，给定排水体积、推力和阻力系数。
- 生成水下航行体一维发射动力学脚本，分析位移、速度和加速度。
- build an underwater torpedo launch model with buoyancy, hydrodynamic drag, and thrust.

反混淆提示：
- 如果问题强调“火箭、垂直发射、空气阻力、燃料消耗”，更接近 `launch_dynamics`。
- 如果问题强调“发射角、导弹、二维轨迹、射程”，更接近 `trajectory_ode`。
- 如果问题只说“发射模型”但未给出介质和对象，必须先澄清是水下发射还是空中发射。
