addpath('D:/python/rag_crm_agent/generated_builds/20260320_030823_frontend_default_env_probe_cadb62bc/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260320_030823_frontend_default_env_probe_cadb62bc/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C++';
cfg.GenerateReport = true;
cfg.GenCodeOnly = true;

codegen -config cfg rocket_launch_1d -args {1.0, 1.0, 1.0, zeros(3,1), zeros(2,1)};
exit;
