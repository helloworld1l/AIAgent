function [y, f] = rocket_launch_1d(mode, time, Ts, x, u)
    INIT = 10102;  % 初始化模式
    CONT = 10103;  % 连续计算模式
    OUT  = 10111;  % 输出模式
    EXIT = 10106;  % 退出模式

    mass0 = 500.0;
    dry_mass = 320.0;
    burn_rate = 2.5;
    thrust_default = 16000.0;
    Cd = 0.55;
    A = 0.8;
    rho0 = 1.225;
    g0 = 9.81;

    state_dim = max(0, 3);
    output_dim = max(0, 2);
    input_dim = max(0, 2);

    if nargin < 4 || isempty(x)
        x = [0; 0; mass0];
    else
        x = x(:);
    end
    if state_dim == 0
        x = zeros(0, 1);
    elseif numel(x) < state_dim
        x = [x; zeros(state_dim - numel(x), 1)];
    elseif numel(x) > state_dim
        x = x(1:state_dim);
    end

    if nargin < 5 || isempty(u)
        u = [thrust_default; 90];
    else
        u = u(:);
    end
    if input_dim == 0
        u = zeros(0, 1);
    elseif numel(u) < input_dim
        u = [u; zeros(input_dim - numel(u), 1)];
    elseif numel(u) > input_dim
        u = u(1:input_dim);
    end

    switch mode
        case INIT
            y = zeros(output_dim, 1);
            f = zeros(state_dim, 1);
            height = max(x(1), 0);
            velocity = x(2);
            mass = min(max(x(3), dry_mass), mass0);
            thrust_val = max(u(1), 0);
            angle_val = max(min(u(2), 90), 0);
            angle_rad = angle_val * pi / 180;
            rho = rho0 * exp(-height / 8500);
            drag = 0.5 * rho * Cd * A * velocity^2;
            g_h = g0 * (6371 / (6371 + height / 1000))^2;
            if mass > dry_mass && thrust_val > 0
                m_dot = burn_rate;
            else
                m_dot = 0;
                thrust_val = 0;
            end
            thrust_vertical = thrust_val * sin(angle_rad);
            drag_vertical = drag * sin(angle_rad) * sign(-velocity);
            accel = (thrust_vertical + drag_vertical) / max(mass, 0.1) - g_h;
            y(1) = height;
            y(2) = velocity;
            f(1) = velocity * sin(angle_rad);
            f(2) = accel;
            f(3) = -m_dot;

        case CONT
            y = zeros(output_dim, 1);
            f = zeros(state_dim, 1);
            height = max(x(1), 0);
            velocity = x(2);
            mass = min(max(x(3), dry_mass), mass0);
            thrust_val = max(u(1), 0);
            angle_val = max(min(u(2), 90), 0);
            angle_rad = angle_val * pi / 180;
            rho = rho0 * exp(-height / 8500);
            drag = 0.5 * rho * Cd * A * velocity^2;
            g_h = g0 * (6371 / (6371 + height / 1000))^2;
            if mass > dry_mass && thrust_val > 0
                m_dot = burn_rate;
            else
                m_dot = 0;
                thrust_val = 0;
            end
            thrust_vertical = thrust_val * sin(angle_rad);
            drag_vertical = drag * sin(angle_rad) * sign(-velocity);
            accel = (thrust_vertical + drag_vertical) / max(mass, 0.1) - g_h;
            y(1) = height;
            y(2) = velocity;
            f(1) = velocity * sin(angle_rad);
            f(2) = accel;
            f(3) = -m_dot;

        case OUT
            y = zeros(output_dim, 1);
            f = zeros(state_dim, 1);
            height = max(x(1), 0);
            velocity = x(2);
            mass = min(max(x(3), dry_mass), mass0);
            thrust_val = max(u(1), 0);
            angle_val = max(min(u(2), 90), 0);
            angle_rad = angle_val * pi / 180;
            rho = rho0 * exp(-height / 8500);
            drag = 0.5 * rho * Cd * A * velocity^2;
            g_h = g0 * (6371 / (6371 + height / 1000))^2;
            if mass > dry_mass && thrust_val > 0
                m_dot = burn_rate;
            else
                m_dot = 0;
                thrust_val = 0;
            end
            thrust_vertical = thrust_val * sin(angle_rad);
            drag_vertical = drag * sin(angle_rad) * sign(-velocity);
            accel = (thrust_vertical + drag_vertical) / max(mass, 0.1) - g_h;
            y(1) = height;
            y(2) = velocity;

        case EXIT
            y = zeros(output_dim, 1);
            f = zeros(state_dim, 1);

        otherwise
            error('Invalid mode');
    end
end