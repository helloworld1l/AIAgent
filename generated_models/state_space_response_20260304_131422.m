%% Auto-generated MATLAB model: State Space Simulation
clear; clc; close all;

A = [0 1; -2 -3];
B = [0; 1];
C = [1 0];
D = 0;
sys = ss(A, B, C, D);

t = linspace(0, 10, 1000)';
u = ones(size(t));
y = lsim(sys, u, t);

figure('Name', 'State Space Output');
plot(t, y, 'LineWidth', 1.5);
xlabel('Time (s)');
ylabel('Output');
title('State Space Simulation');
grid on;
