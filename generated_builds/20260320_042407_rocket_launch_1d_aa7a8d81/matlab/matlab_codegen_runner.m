addpath('D:/python/rag_crm_agent/generated_builds/20260320_042407_rocket_launch_1d_aa7a8d81/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260320_042407_rocket_launch_1d_aa7a8d81/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;
cfg.GenCodeOnly = true;

codegen -config cfg rocket_launch_1d -args {1.0, 1.0, 1.0, zeros(3,1), zeros(2,1)};
exit;
