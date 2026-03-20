# family prototype：orbital_dynamics

family 名称：`orbital_dynamics`

family 层级：主干 family（trunk）

scene：卫星或航天器在地心平面二体模型下的轨道传播与轨道动力学。核心关注轨道高度、轨道速度、引力参数、近地点远地点、轨道周期与在轨运动，不关注大气层内发射升空段，也不关注二维导弹弹道。

典型对象词：卫星、航天器、轨道、二体、在轨飞行、轨道传播、近地点、远地点、轨道周期。

关键槽位：`altitude0`、`v0`、`dt`、`stop_time`。

反混淆词：垂直发射、起飞质量、燃料消耗、发射角、二维弹道、射程、水下、鱼雷、浮力、卡尔曼跟踪、兰彻斯特。

典型问法：
- 生成一个卫星二体轨道传播 MATLAB 模型，给定初始轨道高度和初始轨道速度。
- 做一个航天器平面轨道动力学仿真，分析轨道形状和周期。
- 构建卫星在轨运行脚本，使用地心引力参数和初始轨道条件。
- build a two-body orbital dynamics model for a satellite with initial altitude and speed.

反混淆提示：
- 如果问题强调“升空、推力、燃料质量、空气阻力”，更接近 `launch_dynamics`。
- 如果问题强调“发射角、平面弹道、导弹射程”，更接近 `trajectory_ode`。
- 如果问题强调“再入大气层前的轨道段”仍可能属于 `orbital_dynamics`，但一旦重点转为再入或大气层内飞行，应转向其他 family。
