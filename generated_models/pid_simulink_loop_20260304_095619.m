%% Auto-generated MATLAB model: PID closed-loop Simulink
clear; clc; close all;

modelName = 'auto_pid_loop_model';
if bdIsLoaded(modelName)
    close_system(modelName, 0);
end
new_system(modelName);
open_system(modelName);

add_block('simulink/Sources/Step', [modelName '/Step'], ...
    'Position', [30 80 60 110]);
add_block('simulink/Math Operations/Sum', [modelName '/Sum'], ...
    'Inputs', '+-', 'Position', [100 78 120 112]);
add_block('simulink/Continuous/PID Controller', [modelName '/PID'], ...
    'P', '1.2', 'I', '0.8', 'D', '0.02', ...
    'Position', [170 70 250 120]);
add_block('simulink/Continuous/Transfer Fcn', [modelName '/Plant'], ...
    'Numerator', '[1]', 'Denominator', '[0.5 1]', ...
    'Position', [300 75 380 115]);
add_block('simulink/Sinks/Scope', [modelName '/Scope'], ...
    'Position', [450 80 480 110]);

add_line(modelName, 'Step/1', 'Sum/1');
add_line(modelName, 'Sum/1', 'PID/1');
add_line(modelName, 'PID/1', 'Plant/1');
add_line(modelName, 'Plant/1', 'Scope/1');
add_line(modelName, 'Plant/1', 'Sum/2');

set_param(modelName, 'StopTime', '20');
sim(modelName);
save_system(modelName, [modelName '.slx']);
