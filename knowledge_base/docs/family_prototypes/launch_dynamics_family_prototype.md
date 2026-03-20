# family prototype：launch_dynamics

family 名称：`launch_dynamics`

family 层级：主干 family（trunk）

scene：火箭、运载火箭或助推器在大气层内的一维垂直发射动力学。核心关注垂直升空、推力、重力、空气阻力、燃料消耗与质量递减，不强调二维平面轨迹，也不强调入轨后的轨道传播。

典型对象词：火箭、运载火箭、助推器、垂直发射、垂直升空、一维发射、单轴上升、推进段。

关键槽位：`mass0`、`fuel_mass`、`thrust`、`burn_rate`、`drag_coeff`、`area`、`dt`、`stop_time`。

反混淆词：二维弹道、发射角、平面轨迹、拦截轨迹、卫星、二体轨道、轨道传播、入轨、水下、鱼雷、潜艇、浮力、出管。

典型问法：
- 构建一个火箭一维垂直发射 MATLAB 模型，考虑推力、重力、阻力和燃料消耗。
- 做一个运载火箭垂直升空仿真，给定起飞质量、燃料质量和燃烧速率。
- 生成单轴上升段动力学脚本，重点看高度、速度和加速度曲线。
- build a 1D vertical rocket launch model with thrust, drag, gravity, and fuel burn.

反混淆提示：
- 如果问题里强调“发射角、二维、射程、弹道、拦截”，更接近 `trajectory_ode`。
- 如果问题里强调“卫星、二体、近地点、远地点、轨道周期”，更接近 `orbital_dynamics`。
- 如果问题里强调“鱼雷、潜艇、水阻、浮力、出管”，更接近 `underwater_launch`。
