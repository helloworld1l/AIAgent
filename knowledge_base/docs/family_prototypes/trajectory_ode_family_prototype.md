# family prototype：trajectory_ode

family 名称：`trajectory_ode`

family 层级：主干 family（trunk）

scene：导弹、拦截弹或一般飞行器在二维平面中的飞行轨迹与弹道动力学。核心关注发射角、初速度、平面位置速度演化、射程高度关系与推进段轨迹，不是纯一维垂直升空，也不是入轨后的卫星轨道传播。

典型对象词：导弹、拦截弹、飞行轨迹、二维弹道、平面轨迹、发射角、射程、弹道飞行。

关键槽位：`mass0`、`thrust`、`launch_angle_deg`、`init_speed`、`burn_time`、`drag_coeff`、`dt`、`stop_time`。

反混淆词：垂直升空、一维发射、推重比、卫星、轨道传播、二体、水下、鱼雷、浮力、卡尔曼、跟踪估计、红蓝兵力。

典型问法：
- 生成一个二维导弹飞行轨迹 MATLAB 模型，给定发射角和初速度。
- 做一个拦截弹平面弹道仿真，分析射程和高度随时间的变化。
- 构建二维飞行轨迹脚本，考虑推力、空气阻力和重力。
- build a planar missile trajectory model with launch angle, initial speed, and drag.

反混淆提示：
- 如果重点是“垂直发射、一维升空、燃料质量、推重比”，更接近 `launch_dynamics`。
- 如果重点是“卫星、轨道半径、引力参数、轨道周期”，更接近 `orbital_dynamics`。
- 如果重点是“鱼雷水下出管、浮力、水阻”，更接近 `underwater_launch`。
