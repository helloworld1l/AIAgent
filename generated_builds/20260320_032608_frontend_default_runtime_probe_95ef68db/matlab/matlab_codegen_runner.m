addpath('D:/python/rag_crm_agent/generated_builds/20260320_032608_frontend_default_runtime_probe_95ef68db/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260320_032608_frontend_default_runtime_probe_95ef68db/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;
cfg.GenCodeOnly = true;

codegen -config cfg rocket_launch_1d -args {1.0, 1.0, 1.0, zeros(3,1), zeros(2,1)};
exit;
