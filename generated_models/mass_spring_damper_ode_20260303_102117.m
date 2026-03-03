%% Auto-generated MATLAB model: Mass-Spring-Damper
clear; clc; close all;

m = 2.0;
c = 0.4;
k = 18.0;
x0 = [0; 0];
tspan = [0 2.0];

f = @(t, x) [x(2); -(c/m)*x(2) - (k/m)*x(1)];
[t, x] = ode45(f, tspan, x0);

figure('Name', 'Mass-Spring-Damper');
subplot(2,1,1);
plot(t, x(:,1), 'LineWidth', 1.5); grid on;
ylabel('Displacement (m)');
subplot(2,1,2);
plot(t, x(:,2), 'LineWidth', 1.5); grid on;
xlabel('Time (s)'); ylabel('Velocity (m/s)');
