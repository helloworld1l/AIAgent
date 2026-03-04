%% Auto-generated MATLAB model: Transfer Function Step Response
clear; clc; close all;

num = [1 3 2];
den = [1 3 2];
sys = tf(num, den);

figure('Name', 'Step Response');
step(sys, 10);
grid on;
title('Transfer Function Step Response');

info = stepinfo(sys);
disp(info);
