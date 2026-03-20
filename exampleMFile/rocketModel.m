%% 简化版火箭模型 - 避免Coder变量混淆
% 文件名: rocketModel_simple.m


function [y, f] = rocketModel(mode, time, Ts, x, u)
    INIT = 10102;  % 初始化模式
    CONT = 10103;  % 连续计算模式
    OUT  = 10111;  % 输出模式
    EXIT = 10106;  % 退出模式
    
    switch mode
        case INIT
            % 初始化输出
            y = zeros(2, 1);
            f = zeros(3, 1);
            
            % 参数边界保护
            if isempty(x) || length(x) ~= 3
                x = [0; 0; 1000];
            end
            if isempty(u) || length(u) ~= 2
                u = [50000; 90];
            end
            
            % 确保数值有效
            x(1) = max(x(1), 0);    % 高度 ≥ 0
            x(2) = min(x(2), 0);    % 速度 <=0
            x(3) = max(x(3), 1000);  % 质量 ≥ 100
            u(1) = max(u(1), 50000);    % 推力 ≥ 0
            u(2) = max(max(u(2), 90), 0);  % 角度 0-90度
            % 初始化模式
            y(1) = x(1);  % 输出高度
            
            % 质量流量计算
            if x(3) > 100
                m_dot = u(1) / (300 * 9.81);
            else
                m_dot = 0;
            end
            
            % 状态导数
            f(1) = x(2);                    % 高度导数 = 速度
            f(2) = u(1) / max(x(3), 0.1) - 9.81;  % 速度导数
            f(3) = -m_dot;                  % 质量导数
            
        case CONT
            % 连续计算模式
            y = zeros(2, 1);
            y(1) = x(1);
            
            % 获取参数
            height = max(x(1), 0);
            velocity = x(2);
            mass = max(x(3), 100);
            thrust_val = max(u(1), 0);
            angle_val = max(min(u(2), 90), 0);
            
            % 角度转弧度
            angle_rad = angle_val * pi / 180;
            
            % 大气密度
            rho = 1.225 * exp(-height / 8500);
            
            % 阻力
            drag = 0.5 * rho * velocity^2 * 0.5 * 1.0;
            
            % 重力修正
            g_h = 9.81 * (6371 / (6371 + height/1000))^2;
            
            % 质量流量
            if mass > 100
                m_dot = thrust_val / (300 * 9.81);
            else
                m_dot = 0;
                thrust_val = 0;
            end
            
            % 垂直分量
            thrust_vertical = thrust_val * sin(angle_rad);
            drag_vertical = drag * sin(angle_rad) * sign(-velocity);
            
            % 状态导数
            f = zeros(3, 1);
            f(1) = velocity * sin(angle_rad);
            f(2) = (thrust_vertical + drag_vertical) / max(mass, 0.1) - g_h;
            f(3) = -m_dot;
            
        case OUT
            % 输出模式
            y = zeros(2, 1);
            y(1) = x(1);
            f = [0; 0; 0];
            
        case EXIT
            % 退出模式
            y = zeros(2, 1);
            y(1) = 0;
            f = [0; 0; 0];
            
        otherwise
            error('Invalid mode');
    end
    
    y(2) = 0;  % 第二个输出始终为0
end