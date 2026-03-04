%% Auto-generated MATLAB model: MPC demo
clear; clc; close all;

Ts = 0.1;
plant = tf(1, [1 1 0]);
plant_d = c2d(ss(plant), Ts);

mpcobj = mpc(plant_d, Ts, 20, 5);
mpcobj.MV.Min = -1;
mpcobj.MV.Max = 1;
mpcobj.Weights.OutputVariables = 1;
mpcobj.Weights.ManipulatedVariablesRate = 0.1;

T = 30.0;
r = ones(T/Ts,1);
sim(mpcobj, length(r), r);
