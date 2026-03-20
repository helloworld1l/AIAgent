%% Auto-generated MATLAB model: Kalman tracking
clear; clc; close all;
rng(7);

dt = 0.1;
N = 200;
q = 0.01;
r = 0.1;

F = [1 dt; 0 1];
H = [1 0];
Q = q * [dt^4/4 dt^3/2; dt^3/2 dt^2];
R = r;

x_true = zeros(2, N);
z = zeros(1, N);
x_true(:,1) = [0; 1];
for k = 2:N
    w = mvnrnd([0 0], Q)';
    x_true(:,k) = F * x_true(:,k-1) + w;
end
for k = 1:N
    z(k) = H*x_true(:,k) + sqrt(R)*randn;
end

x_est = zeros(2, N);
P = eye(2);
for k = 2:N
    x_pred = F*x_est(:,k-1);
    P_pred = F*P*F' + Q;
    K = P_pred*H'/(H*P_pred*H' + R);
    x_est(:,k) = x_pred + K*(z(k) - H*x_pred);
    P = (eye(2)-K*H)*P_pred;
end

t = (0:N-1)*dt;
figure('Name', 'Kalman Tracking');
plot(t, x_true(1,:), 'k-', 'LineWidth', 1.5); hold on;
plot(t, z, '.', 'Color', [0.6 0.6 0.6]);
plot(t, x_est(1,:), 'r-', 'LineWidth', 1.5);
legend('True', 'Measurement', 'Estimated');
xlabel('Time (s)'); ylabel('Position'); grid on;
