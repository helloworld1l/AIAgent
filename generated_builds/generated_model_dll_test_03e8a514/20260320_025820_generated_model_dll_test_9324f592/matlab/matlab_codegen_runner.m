addpath('D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_03e8a514/20260320_025820_generated_model_dll_test_9324f592/inputs');
cd('D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_03e8a514/20260320_025820_generated_model_dll_test_9324f592/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;
cfg.GenCodeOnly = true;

codegen -config cfg rocket_launch_1d -args {1.0, 1.0, 1.0, zeros(3,1), zeros(2,1)};
exit;
