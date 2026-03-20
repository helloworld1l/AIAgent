addpath('D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/inputs');
cd('D:/python/rag_crm_agent/generated_builds/generated_model_dll_test_c46f76e2/20260319_073444_generated_model_dll_test_4237ebd6/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;
cfg.GenCodeOnly = true;

codegen -config cfg rocket_launch_1d -args {1.0, 1.0, 1.0, zeros(3,1), zeros(2,1)};
exit;
